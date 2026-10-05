//go:build !windows
// +build !windows

// Installer for the pinned toolchain on Linux and macOS.
//
// The canonical inventory is tooling/.tool-versions.  This program deliberately
// does not install "latest" versions or execute downloaded shell scripts.  It
// uses an already-installed asdf, Homebrew, apt-get, or dnf installation path
// only when the requested version can be passed explicitly and is verified
// after installation.  If an exact version cannot be installed safely, the
// program fails closed with remediation guidance.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	exitOK          = 0
	exitValidation  = 2
	exitInstall     = 3
	exitVerify      = 4
	exitUnsupported = 5
	exitInterrupted = 130
)

type version struct {
	major int
	minor int
	patch int
}

func (v version) String() string {
	return fmt.Sprintf("%d.%d.%d", v.major, v.minor, v.patch)
}

type toolSpec struct {
	Name        string
	Executables []string
	VersionArgs []string
	AsdfPlugin  string
	BrewFormula string
	AptPackage  string
	DNFPackage  string
	PatchTolerance int
}

type config struct {
	Root        string
	Platform    string
	DryRun      bool
	NonInteract bool
	Verbose     bool
	Force       bool
	Timeout     time.Duration
	InstallDir  string
	Runner      func(context.Context, string, ...string) (string, error)
}

type toolResult struct {
	Name          string
	Version       string
	Status        string
	VerifyFailure bool
	Err           error
}

var (
	concreteVersionPattern = regexp.MustCompile(`^(?:v)?[0-9]+\.[0-9]+\.[0-9]+$`)
	versionPattern         = regexp.MustCompile(`(?i)(?:^|[^0-9])v?([0-9]+)\.([0-9]+)(?:\.([0-9]+))?(?:[^0-9]|$)`)
	toolNamePattern        = regexp.MustCompile(`^[A-Za-z0-9_.-]+$`)
)

var toolSpecs = map[string]toolSpec{
	"terraform":         {Name: "terraform", Executables: []string{"terraform"}, VersionArgs: []string{"version"}, AsdfPlugin: "terraform", BrewFormula: "terraform", AptPackage: "terraform", DNFPackage: "terraform"},
	"terragrunt":        {Name: "terragrunt", Executables: []string{"terragrunt"}, VersionArgs: []string{"--version"}, AsdfPlugin: "terragrunt", BrewFormula: "terragrunt"},
	"golang":            {Name: "golang", Executables: []string{"go"}, VersionArgs: []string{"version"}, AsdfPlugin: "golang", BrewFormula: "go", AptPackage: "golang", DNFPackage: "golang", PatchTolerance: 9},
	"python":            {Name: "python", Executables: []string{"python3", "python"}, VersionArgs: []string{"--version"}, AsdfPlugin: "python", BrewFormula: "python", AptPackage: "python3", DNFPackage: "python3"},
	"nodejs":            {Name: "nodejs", Executables: []string{"node"}, VersionArgs: []string{"--version"}, AsdfPlugin: "nodejs", BrewFormula: "node", AptPackage: "nodejs", DNFPackage: "nodejs"},
	"awscli":            {Name: "awscli", Executables: []string{"aws"}, VersionArgs: []string{"--version"}, AsdfPlugin: "awscli", BrewFormula: "awscli", AptPackage: "awscli", DNFPackage: "awscli"},
	"docker-cli":        {Name: "docker-cli", Executables: []string{"docker"}, VersionArgs: []string{"--version"}, AsdfPlugin: "docker", BrewFormula: "docker", AptPackage: "docker.io", DNFPackage: "docker"},
	"tflint":            {Name: "tflint", Executables: []string{"tflint"}, VersionArgs: []string{"--version"}, AsdfPlugin: "tflint", BrewFormula: "tflint"},
	"trivy":             {Name: "trivy", Executables: []string{"trivy"}, VersionArgs: []string{"--version"}, AsdfPlugin: "trivy", BrewFormula: "trivy"},
	"checkov":           {Name: "checkov", Executables: []string{"checkov"}, VersionArgs: []string{"--version"}, AsdfPlugin: "checkov", BrewFormula: "checkov"},
	"yamllint":          {Name: "yamllint", Executables: []string{"yamllint"}, VersionArgs: []string{"--version"}, AsdfPlugin: "yamllint", BrewFormula: "yamllint"},
	"shellcheck":        {Name: "shellcheck", Executables: []string{"shellcheck"}, VersionArgs: []string{"--version"}, AsdfPlugin: "shellcheck", BrewFormula: "shellcheck", AptPackage: "shellcheck", DNFPackage: "ShellCheck"},
	"shfmt":             {Name: "shfmt", Executables: []string{"shfmt"}, VersionArgs: []string{"--version"}, AsdfPlugin: "shfmt", BrewFormula: "shfmt"},
	"markdownlint-cli2": {Name: "markdownlint-cli2", Executables: []string{"markdownlint-cli2"}, VersionArgs: []string{"--version"}, AsdfPlugin: "markdownlint-cli2", BrewFormula: "markdownlint-cli2"},
	"gitleaks":          {Name: "gitleaks", Executables: []string{"gitleaks"}, VersionArgs: []string{"version"}, AsdfPlugin: "gitleaks", BrewFormula: "gitleaks"},
	"actionlint":        {Name: "actionlint", Executables: []string{"actionlint"}, VersionArgs: []string{"-version"}, AsdfPlugin: "actionlint", BrewFormula: "actionlint"},
	"golangci-lint":     {Name: "golangci-lint", Executables: []string{"golangci-lint"}, VersionArgs: []string{"version"}, AsdfPlugin: "golangci-lint", BrewFormula: "golangci-lint"},
	"task":              {Name: "task", Executables: []string{"task"}, VersionArgs: []string{"--version"}, AsdfPlugin: "task", BrewFormula: "go-task", AptPackage: "go-task", DNFPackage: "go-task"},
	"just":              {Name: "just", Executables: []string{"just"}, VersionArgs: []string{"--version"}, AsdfPlugin: "just", BrewFormula: "just"},
	"make":              {Name: "make", Executables: []string{"gmake", "make"}, VersionArgs: []string{"--version"}, AsdfPlugin: "make", BrewFormula: "make", AptPackage: "make", DNFPackage: "make"},
	"pre-commit":        {Name: "pre-commit", Executables: []string{"pre-commit"}, VersionArgs: []string{"--version"}, AsdfPlugin: "pre-commit", BrewFormula: "pre-commit", AptPackage: "pre-commit", DNFPackage: "pre-commit"},
	"jq":                {Name: "jq", Executables: []string{"jq"}, VersionArgs: []string{"--version"}, AsdfPlugin: "jq", BrewFormula: "jq", AptPackage: "jq", DNFPackage: "jq"},
	"yq":                {Name: "yq", Executables: []string{"yq"}, VersionArgs: []string{"--version"}, AsdfPlugin: "yq", BrewFormula: "yq"},
}

func parseVersion(raw string) (version, error) {
	raw = strings.TrimSpace(strings.TrimPrefix(raw, "v"))
	parts := strings.Split(raw, ".")
	if len(parts) != 3 {
		return version{}, fmt.Errorf("version %q must be major.minor.patch", raw)
	}
	values := [3]int{}
	for i, part := range parts {
		if part == "" {
			return version{}, fmt.Errorf("version %q has an empty component", raw)
		}
		value, err := strconv.Atoi(part)
		if err != nil || value < 0 {
			return version{}, fmt.Errorf("version %q has a non-numeric component", raw)
		}
		values[i] = value
	}
	return version{major: values[0], minor: values[1], patch: values[2]}, nil
}

func parseToolVersions(data string) ([]string, map[string]string, error) {
	order := make([]string, 0)
	versions := make(map[string]string)
	for lineNo, raw := range strings.Split(strings.TrimPrefix(data, "\ufeff"), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if index := strings.Index(line, "#"); index >= 0 {
			line = strings.TrimSpace(line[:index])
		}
		fields := strings.Fields(line)
		if len(fields) != 2 {
			return nil, nil, fmt.Errorf("line %d: expected exactly '<tool> <version>'", lineNo+1)
		}
		name, requested := fields[0], fields[1]
		if !toolNamePattern.MatchString(name) {
			return nil, nil, fmt.Errorf("line %d: invalid tool name %q", lineNo+1, name)
		}
		if _, exists := versions[name]; exists {
			return nil, nil, fmt.Errorf("line %d: duplicate tool %q", lineNo+1, name)
		}
		if !concreteVersionPattern.MatchString(requested) {
			return nil, nil, fmt.Errorf("line %d: %s has a non-concrete version %q", lineNo+1, name, requested)
		}
		if _, err := parseVersion(requested); err != nil {
			return nil, nil, fmt.Errorf("line %d: %w", lineNo+1, err)
		}
		versions[name] = strings.TrimPrefix(requested, "v")
		order = append(order, name)
	}
	if len(order) == 0 {
		return nil, nil, errors.New("tool-version file contains no active entries")
	}
	return order, versions, nil
}

func validateMirror(source, mirror map[string]string) error {
	if len(source) != len(mirror) {
		return fmt.Errorf("mirror inventory differs from canonical file: canonical=%d mirror=%d", len(source), len(mirror))
	}
	for name, expected := range source {
		actual, ok := mirror[name]
		if !ok {
			return fmt.Errorf("mirror is missing tool %q", name)
		}
		ev, _ := parseVersion(expected)
		av, err := parseVersion(actual)
		if err != nil || ev != av {
			return fmt.Errorf("mirror version mismatch for %s: canonical=%s mirror=%s", name, expected, actual)
		}
	}
	return nil
}

func parseGoDirective(root string) (version, error) {
	data, err := os.ReadFile(filepath.Join(root, "go.mod"))
	if err != nil {
		return version{}, fmt.Errorf("read go.mod: %w", err)
	}
	var declared string
	for lineNo, raw := range strings.Split(string(data), "\n") {
		fields := strings.Fields(strings.TrimSpace(raw))
		if len(fields) >= 2 && fields[0] == "go" {
			if declared != "" {
				return version{}, fmt.Errorf("go.mod contains duplicate go directives (line %d)", lineNo+1)
			}
			declared = fields[1]
		}
	}
	if declared == "" {
		return version{}, errors.New("go.mod does not contain a go directive")
	}
	parts := strings.Split(strings.TrimPrefix(declared, "v"), ".")
	if len(parts) == 2 {
		parts = append(parts, "0")
	}
	if len(parts) != 3 {
		return version{}, fmt.Errorf("go.mod go directive %q is malformed", declared)
	}
	return parseVersion(strings.Join(parts, "."))
}

func validateGoVersion(root, requested string) error {
	expected, err := parseVersion(requested)
	if err != nil {
		return fmt.Errorf("parse golang pin: %w", err)
	}
	declared, err := parseGoDirective(root)
	if err != nil {
		return err
	}
	if expected.major != declared.major || expected.minor != declared.minor ||
		(declared.patch != 0 && expected.patch != declared.patch) {
		return fmt.Errorf("golang %s is incompatible with go.mod %s", requested, declared)
	}
	return nil
}

func resolveRoot(override string) (string, error) {
	if override != "" {
		root, err := filepath.Abs(override)
		if err != nil {
			return "", fmt.Errorf("resolve --root: %w", err)
		}
		if !fileExists(filepath.Join(root, "tooling", ".tool-versions")) {
			return "", fmt.Errorf("repository root does not contain tooling/.tool-versions: %s", root)
		}
		return filepath.Clean(root), nil
	}
	candidates := make([]string, 0, 3)
	if cwd, err := os.Getwd(); err == nil {
		candidates = append(candidates, cwd)
	}
	if _, source, _, ok := runtime.Caller(0); ok {
		candidates = append(candidates, filepath.Dir(source))
	}
	if executable, err := os.Executable(); err == nil {
		candidates = append(candidates, filepath.Dir(executable))
	}
	seen := map[string]bool{}
	for _, candidate := range candidates {
		for dir := filepath.Clean(candidate); ; dir = filepath.Dir(dir) {
			if seen[dir] {
				break
			}
			seen[dir] = true
			if fileExists(filepath.Join(dir, "tooling", ".tool-versions")) {
				return dir, nil
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
		}
	}
	return "", errors.New("repository root not found; pass --root explicitly")
}

func fileExists(path string) bool {
	info, err := os.Stat(path)
	return err == nil && !info.IsDir()
}

func commandRunner(ctx context.Context, name string, args ...string) (string, error) {
	command := exec.CommandContext(ctx, name, args...)
	var output bytes.Buffer
	command.Stdout = &output
	command.Stderr = &output
	if err := command.Run(); err != nil {
		return output.String(), fmt.Errorf("%s %s: %w: %s", name, strings.Join(args, " "), err, strings.TrimSpace(output.String()))
	}
	return output.String(), nil
}

func parseOutputVersion(output string) (string, error) {
	match := versionPattern.FindStringSubmatch(output)
	if match == nil {
		return "", fmt.Errorf("unable to parse a semantic version from %q", strings.TrimSpace(output))
	}
	patch := match[3]
	if patch == "" {
		patch = "0"
	}
	parsed, err := parseVersion(match[1] + "." + match[2] + "." + patch)
	if err != nil {
		return "", err
	}
	return parsed.String(), nil
}

func versionSatisfies(detectedStr, requiredStr string, patchTolerance int) bool {
	if patchTolerance == 0 {
		return detectedStr == requiredStr
	}
	detected, err := parseVersion(detectedStr)
	if err != nil {
		return false
	}
	required, err := parseVersion(requiredStr)
	if err != nil {
		return false
	}
	return detected.major == required.major &&
		detected.minor == required.minor &&
		detected.patch >= required.patch &&
		detected.patch <= required.patch+patchTolerance
}

func prependPath(dir string) {
	if dir == "" {
		return
	}
	absolute, err := filepath.Abs(dir)
	if err != nil {
		return
	}
	for _, existing := range filepath.SplitList(os.Getenv("PATH")) {
		if filepath.Clean(existing) == filepath.Clean(absolute) {
			return
		}
	}
	_ = os.Setenv("PATH", absolute+string(os.PathListSeparator)+os.Getenv("PATH"))
}

func prepareToolPath(installDir string) {
	prependPath(installDir)
	home, err := os.UserHomeDir()
	if err != nil {
		home = os.Getenv("HOME")
	}
	asdfRoot := os.Getenv("ASDF_DATA_DIR")
	if asdfRoot == "" {
		asdfRoot = filepath.Join(home, ".asdf")
	}
	prependPath(filepath.Join(asdfRoot, "shims"))
	prependPath(filepath.Join(asdfRoot, "bin"))
	miseData := os.Getenv("MISE_DATA_DIR")
	if miseData == "" {
		miseData = filepath.Join(home, ".local", "share", "mise")
	}
	prependPath(filepath.Join(miseData, "shims"))
}

func repairPipToolPath(ctx context.Context, runner func(context.Context, string, ...string) (string, error)) {
	if home, err := os.UserHomeDir(); err == nil {
		prependPath(filepath.Join(home, ".local", "bin"))
	}
	for _, py := range []string{"python3", "python"} {
		if _, err := exec.LookPath(py); err != nil {
			continue
		}
		if out, err := runner(ctx, py, "-c",
			"import sysconfig; print(sysconfig.get_path('scripts', 'posix_user'))"); err == nil {
			if p := strings.TrimSpace(out); p != "" {
				prependPath(p)
			}
		}
		if out, err := runner(ctx, py, "-c",
			"import sysconfig; print(sysconfig.get_path('scripts'))"); err == nil {
			if p := strings.TrimSpace(out); p != "" {
				prependPath(p)
			}
		}
		break
	}
}
func installPipTool(ctx context.Context, cfg config, toolName, requested string) error {
	pkg := toolName + "==" + requested
	if cfg.DryRun {
		fmt.Printf("dry-run: would run python -m pip install --user %s\n", pkg)
		return nil
	}
	runner := cfg.Runner
	if runner == nil {
		runner = commandRunner
	}
	for _, py := range []string{"python3", "python"} {
		if _, err := exec.LookPath(py); err != nil {
			continue
		}
		if _, err := runner(ctx, py, "-m", "pip", "install", "--user", pkg); err != nil {
			return fmt.Errorf("pip install --user %s: %w", pkg, err)
		}
		repairPipToolPath(ctx, runner)
		return nil
	}
	return fmt.Errorf("no Python interpreter found; cannot install %s via pip", toolName)
}

func installYamllint(ctx context.Context, cfg config, requested string) error {
	return installPipTool(ctx, cfg, "yamllint", requested)
}

type posixInstallerFn func(context.Context, config, string) error

var directInstallers = map[string]posixInstallerFn{
	"yamllint": installYamllint,
}

func findInstalled(spec toolSpec, runner func(context.Context, string, ...string) (string, error), ctx context.Context) (string, string, error) {
	var lastErr error
	for _, candidate := range spec.Executables {
		executable, err := exec.LookPath(candidate)
		if err != nil {
			lastErr = err
			continue
		}
		output, err := runner(ctx, executable, spec.VersionArgs...)
		if err != nil {
			lastErr = err
			continue
		}
		version, err := parseOutputVersion(output)
		if err != nil {
			lastErr = fmt.Errorf("%s: %w", executable, err)
			continue
		}
		return executable, version, nil
	}
	if lastErr == nil {
		lastErr = errors.New("executable not found")
	}
	return "", "", lastErr
}

func normalizePlatform(value string) (string, error) {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "linux":
		return "linux", nil
	case "darwin", "macos", "osx":
		return "macos", nil
	case "posix":
		if runtime.GOOS == "darwin" {
			return "macos", nil
		}
		return "linux", nil
	default:
		return "", fmt.Errorf("unsupported POSIX platform %q; supported values are linux and macos", value)
	}
}

func detectPlatform(explicit string) (string, error) {
	if explicit != "" {
		return normalizePlatform(explicit)
	}
	for _, variable := range []string{"CROSS_PLATFORM_PLATFORM", "BOOTSTRAP_WRAPPER_OS", "SETUP_PLATFORM"} {
		if value := os.Getenv(variable); strings.TrimSpace(value) != "" {
			return normalizePlatform(value)
		}
	}
	return normalizePlatform(runtime.GOOS)
}

func validateArchitecture() error {
	switch runtime.GOARCH {
	case "amd64", "arm64":
		return nil
	default:
		return fmt.Errorf("unsupported architecture %q; supported architectures are amd64 and arm64", runtime.GOARCH)
	}
}

func runAsdf(ctx context.Context, cfg config, spec toolSpec, requested string) error {
	if _, err := exec.LookPath("asdf"); err != nil {
		return errors.New("asdf is not available")
	}
	plugins, err := cfg.Runner(ctx, "asdf", "plugin", "list")
	if err != nil {
		return fmt.Errorf("list asdf plugins: %w", err)
	}
	found := false
	for _, plugin := range strings.Fields(plugins) {
		if plugin == spec.AsdfPlugin {
			found = true
			break
		}
	}
	if !found {
		return fmt.Errorf("asdf plugin %q is not installed; add and audit the official plugin before rerunning", spec.AsdfPlugin)
	}
	if cfg.DryRun {
		fmt.Printf("dry-run: would run asdf install %s %s\n", spec.AsdfPlugin, requested)
		return nil
	}
	if _, err := cfg.Runner(ctx, "asdf", "install", spec.AsdfPlugin, requested); err != nil {
		return fmt.Errorf("asdf install %s %s: %w", spec.AsdfPlugin, requested, err)
	}
	prefix, err := cfg.Runner(ctx, "asdf", "where", spec.AsdfPlugin, requested)
	if err != nil {
		return fmt.Errorf("resolve asdf installation path for %s %s: %w", spec.AsdfPlugin, requested, err)
	}
	prefix = strings.TrimSpace(prefix)
	if prefix == "" {
		return errors.New("asdf returned an empty installation path")
	}
	bin := filepath.Join(prefix, "bin")
	current := os.Getenv("PATH")
	if _, err := os.Stat(bin); err == nil {
		_ = os.Setenv("PATH", bin+string(os.PathListSeparator)+current)
	}
	return nil
}

func runPackageManager(ctx context.Context, cfg config, platform string, spec toolSpec, requested string) error {
	switch platform {
	case "macos":
		if _, err := exec.LookPath("brew"); err != nil {
			return errors.New("Homebrew is not installed")
		}
		if spec.BrewFormula == "" {
			return errors.New("no Homebrew formula mapping exists")
		}
		formula := spec.BrewFormula
		if spec.Name == "python" {
			parsed, parseErr := parseVersion(requested)
			if parseErr != nil {
				return parseErr
			}
			formula = fmt.Sprintf("python@%d.%d", parsed.major, parsed.minor)
		}
		if cfg.DryRun {
			fmt.Printf("dry-run: would run brew install %s\n", formula)
			return nil
		}
		exact, err := brewHasExactVersion(ctx, cfg, formula, requested)
		if err != nil {
			return err
		}
		if !exact {
			return fmt.Errorf("Homebrew formula %s does not expose exact version %s", formula, requested)
		}
		if _, err := cfg.Runner(ctx, "brew", "install", formula); err != nil {
			return fmt.Errorf("brew install %s: %w", formula, err)
		}
		return nil
	case "linux":
		if _, err := exec.LookPath("apt-get"); err == nil && spec.AptPackage != "" {
			if cfg.DryRun {
				fmt.Printf("dry-run: would run apt-get install %s=%s\n", spec.AptPackage, requested)
				return nil
			}
			args := []string{"install", "-y", spec.AptPackage + "=" + requested}
			if os.Geteuid() != 0 {
				if _, err := exec.LookPath("sudo"); err != nil {
					return errors.New("apt-get installation requires root or sudo")
				}
				args = append([]string{"-n", "apt-get"}, args...)
				if _, err := cfg.Runner(ctx, "sudo", args...); err != nil {
					return fmt.Errorf("sudo apt-get install %s=%s: %w", spec.AptPackage, requested, err)
				}
				return nil
			}
			if _, err := cfg.Runner(ctx, "apt-get", args...); err != nil {
				return fmt.Errorf("apt-get install %s=%s: %w", spec.AptPackage, requested, err)
			}
			return nil
		}
		if _, err := exec.LookPath("dnf"); err == nil && spec.DNFPackage != "" {
			if cfg.DryRun {
				fmt.Printf("dry-run: would run dnf install %s-%s\n", spec.DNFPackage, requested)
				return nil
			}
			args := []string{"install", "-y", spec.DNFPackage + "-" + requested}
			command := "dnf"
			if os.Geteuid() != 0 {
				if _, err := exec.LookPath("sudo"); err != nil {
					return errors.New("dnf installation requires root or sudo")
				}
				command = "sudo"
				args = append([]string{"-n", "dnf"}, args...)
			}
			if _, err := cfg.Runner(ctx, command, args...); err != nil {
				return fmt.Errorf("%s install %s-%s: %w", command, spec.DNFPackage, requested, err)
			}
			return nil
		}
		return errors.New("no supported Linux package manager with an exact-version mapping is available")
	default:
		return fmt.Errorf("unsupported platform %s", platform)
	}
}

func brewHasExactVersion(ctx context.Context, cfg config, formula, requested string) (bool, error) {
	output, err := cfg.Runner(ctx, "brew", "info", "--json=v2", "--formula", formula)
	if err != nil {
		return false, fmt.Errorf("inspect Homebrew formula %s: %w", formula, err)
	}
	var payload struct {
		Formulae []struct {
			Versions struct {
				Stable string `json:"stable"`
			} `json:"versions"`
		} `json:"formulae"`
	}
	if err := json.Unmarshal([]byte(output), &payload); err != nil {
		return false, fmt.Errorf("parse Homebrew metadata for %s: %w", formula, err)
	}
	if len(payload.Formulae) != 1 {
		return false, fmt.Errorf("Homebrew metadata for %s is ambiguous", formula)
	}
	actual, err := parseVersion(payload.Formulae[0].Versions.Stable)
	if err != nil {
		return false, fmt.Errorf("Homebrew metadata for %s has invalid stable version: %w", formula, err)
	}
	expected, err := parseVersion(requested)
	if err != nil {
		return false, err
	}
	return actual == expected, nil
}

func installTool(ctx context.Context, cfg config, platform, name, requested string) toolResult {
	result := toolResult{Name: name, Version: requested}
	spec := toolSpecs[name]
	runner := cfg.Runner
	if runner == nil {
		runner = commandRunner
	}
	if executable, current, err := findInstalled(spec, runner, ctx); err == nil {
		if versionSatisfies(current, requested, spec.PatchTolerance) && !cfg.Force {
			fmt.Printf("%s %s already satisfied (%s)\n", name, requested, executable)
			result.Status = "already-satisfied"
			return result
		}
		fmt.Printf("%s is %s; required %s\n", name, current, requested)
	}
	if installer, ok := directInstallers[name]; ok {
		if err := installer(ctx, cfg, requested); err != nil {
			result.Status = "failed"
			result.Err = fmt.Errorf("install %s %s: %w", name, requested, err)
			return result
		}
		if cfg.DryRun {
			result.Status = "would-install"
			return result
		}
		goto verify
	}
	if cfg.DryRun {
		fmt.Printf("dry-run: would install %s %s via asdf or the configured %s package manager\n", name, requested, platform)
		result.Status = "would-install"
		return result
	}
	if spec.AsdfPlugin != "" {
		if err := runAsdf(ctx, cfg, spec, requested); err == nil {
			goto verify
		} else if cfg.Verbose {
			fmt.Fprintf(os.Stderr, "%s: asdf path unavailable: %v\n", name, err)
		}
	}
	if err := runPackageManager(ctx, cfg, platform, spec, requested); err != nil {
		result.Status = "failed"
		result.Err = fmt.Errorf("install %s %s: %w", name, requested, err)
		return result
	}
verify:
	prepareToolPath(cfg.InstallDir)
	if executable, current, err := findInstalled(spec, runner, ctx); err != nil {
		result.Status = "failed"
		result.VerifyFailure = true
		result.Err = fmt.Errorf("post-install verification for %s: %w", name, err)
		return result
	} else if !versionSatisfies(current, requested, spec.PatchTolerance) {
		result.Status = "failed"
		result.VerifyFailure = true
		result.Err = fmt.Errorf("post-install version mismatch for %s: required %s, detected %s (%s)", name, requested, current, executable)
		return result
	}
	fmt.Printf("%s %s installed and verified\n", name, requested)
	result.Status = "installed"
	return result
}

func run(cfg config, selected []string) int {
	platform, err := detectPlatform(cfg.Platform)
	if err != nil {
		fmt.Fprintf(os.Stderr, "platform error: %v\n", err)
		return exitUnsupported
	}
	if err := validateArchitecture(); err != nil {
		fmt.Fprintf(os.Stderr, "platform error: %v\n", err)
		return exitUnsupported
	}
	root, err := resolveRoot(cfg.Root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: %v\n", err)
		return exitValidation
	}
	fmt.Printf("repository root: %s\nplatform: %s\n", root, platform)
	prepareToolPath(cfg.InstallDir)
	sourceData, err := os.ReadFile(filepath.Join(root, "tooling", ".tool-versions"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: read .tool-versions: %v\n", err)
		return exitValidation
	}
	order, versions, err := parseToolVersions(string(sourceData))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: %v\n", err)
		return exitValidation
	}
	mirrorData, err := os.ReadFile(filepath.Join(root, "tooling", "cross-platform", "asdf-tool-versions"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: read mirror: %v\n", err)
		return exitValidation
	}
	_, mirror, err := parseToolVersions(string(mirrorData))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: parse mirror: %v\n", err)
		return exitValidation
	}
	if err := validateMirror(versions, mirror); err != nil {
		fmt.Fprintf(os.Stderr, "validation error: %v\n", err)
		return exitValidation
	}
	if requested, ok := versions["golang"]; !ok {
		fmt.Fprintln(os.Stderr, "validation error: golang entry is missing from .tool-versions")
		return exitValidation
	} else if err := validateGoVersion(root, requested); err != nil {
		fmt.Fprintf(os.Stderr, "validation error: %v\n", err)
		return exitValidation
	}
	if len(selected) == 0 {
		selected = append([]string(nil), order...)
	} else {
		known := make(map[string]bool, len(order))
		for _, name := range order {
			known[name] = true
		}
		for _, name := range selected {
			if !known[name] {
				fmt.Fprintf(os.Stderr, "validation error: selected tool %q is not in .tool-versions\n", name)
				return exitValidation
			}
		}
	}
	for _, name := range selected {
		if _, ok := toolSpecs[name]; !ok {
			fmt.Fprintf(os.Stderr, "validation error: no supported POSIX installation mapping for %q\n", name)
			return exitValidation
		}
	}
	sort.SliceStable(selected, func(i, j int) bool {
		return selected[i] < selected[j]
	})
	signalCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	ctx, cancel := context.WithTimeout(signalCtx, cfg.Timeout)
	defer cancel()
	if cfg.Runner == nil {
		cfg.Runner = commandRunner
	}
	results := make([]toolResult, 0, len(selected))
	for _, name := range selected {
		results = append(results, installTool(ctx, cfg, platform, name, versions[name]))
	}
	fmt.Println("\nInstallation summary:")
	failed := 0
	for _, result := range results {
		if result.Err != nil {
			failed++
			fmt.Printf("  %-20s %-12s FAILED: %v\n", result.Name, result.Version, result.Err)
		} else {
			fmt.Printf("  %-20s %-12s %s\n", result.Name, result.Version, result.Status)
		}
	}
	if errors.Is(ctx.Err(), context.Canceled) {
		return exitInterrupted
	}
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return exitInstall
	}
	if failed > 0 {
		for _, result := range results {
			if result.VerifyFailure {
				return exitVerify
			}
		}
		return exitInstall
	}
	return exitOK
}

func main() {
	flags := flag.NewFlagSet(os.Args[0], flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	root := flags.String("root", "", "repository root (default: discover from cwd or source location)")
	platform := flags.String("platform", "", "platform override: linux, macos, darwin, or posix")
	dryRun := flags.Bool("dry-run", false, "validate and print actions without changing the system")
	nonInteractive := flags.Bool("non-interactive", false, "disable interactive package-manager prompts")
	verbose := flags.Bool("verbose", false, "enable verbose diagnostics")
	force := flags.Bool("force", false, "reinstall tools even when the requested version is present")
	timeout := flags.Duration("timeout", 30*time.Minute, "overall operation timeout")
	installDir := flags.String("install-dir", "", "optional directory to prepend to PATH for installed executables")
	if err := flags.Parse(os.Args[1:]); err != nil {
		if errors.Is(err, flag.ErrHelp) {
			os.Exit(exitOK)
		}
		os.Exit(exitValidation)
	}
	if *timeout <= 0 {
		fmt.Fprintln(os.Stderr, "validation error: --timeout must be positive")
		os.Exit(exitValidation)
	}
	if os.Getenv("CI") != "" {
		*nonInteractive = true
	}
	cfg := config{
		Root:        *root,
		Platform:    *platform,
		DryRun:      *dryRun,
		NonInteract: *nonInteractive,
		Verbose:     *verbose,
		Force:       *force,
		Timeout:     *timeout,
		InstallDir:  *installDir,
		Runner:      commandRunner,
	}
	os.Exit(run(cfg, flags.Args()))
}
