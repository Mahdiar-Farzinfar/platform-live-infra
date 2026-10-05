//go:build windows
// +build windows

package main

import (
	"archive/zip"
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path"
	"path/filepath"
	"regexp"
	"runtime"
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

	maxDownloadSize = 100 * 1024 * 1024
	maxChecksumSize = 2 * 1024 * 1024
)

type version struct{ major, minor, patch int }

func (v version) String() string {
	return fmt.Sprintf("%d.%d.%d", v.major, v.minor, v.patch)
}

type toolSpec struct {
	name       string
	scoop      string
	executable string
	args       []string
}

type toolResult struct {
	name             string
	version          string
	status           string
	checksumVerified bool
	verifyFailure    bool
	err              error
}

type config struct {
	root        string
	dryRun      bool
	verbose     bool
	force       bool
	timeout     time.Duration
	httpClient  *http.Client
	commandFunc func(context.Context, string, ...string) (string, error)
}

var versionPattern = regexp.MustCompile(`(?i)(?:^|[^0-9])v?([0-9]+)\.([0-9]+)(?:\.([0-9]+))?(?:[^0-9]|$)`)
var toolNamePattern = regexp.MustCompile(`^[A-Za-z0-9_.-]+$`)
var concreteVersionPattern = regexp.MustCompile(`^(?:v)?[0-9]+\.[0-9]+\.[0-9]+$`)

var toolSpecs = map[string]toolSpec{
	"terraform":         {name: "terraform", scoop: "terraform", executable: "terraform", args: []string{"version"}},
	"terragrunt":        {name: "terragrunt", scoop: "terragrunt", executable: "terragrunt", args: []string{"--version"}},
	"golang":            {name: "golang", scoop: "go", executable: "go", args: []string{"version"}},
	"python":            {name: "python", scoop: "python", executable: "python", args: []string{"--version"}},
	"nodejs":            {name: "nodejs", scoop: "nodejs", executable: "node", args: []string{"--version"}},
	"awscli":            {name: "awscli", scoop: "aws", executable: "aws", args: []string{"--version"}},
	"docker-cli":        {name: "docker-cli", scoop: "docker", executable: "docker", args: []string{"--version"}},
	"tflint":            {name: "tflint", scoop: "tflint", executable: "tflint", args: []string{"--version"}},
	"trivy":             {name: "trivy", scoop: "trivy", executable: "trivy", args: []string{"--version"}},
	"checkov":           {name: "checkov", scoop: "checkov", executable: "checkov", args: []string{"--version"}},
	"yamllint":          {name: "yamllint", scoop: "yamllint", executable: "yamllint", args: []string{"--version"}},
	"shellcheck":        {name: "shellcheck", scoop: "shellcheck", executable: "shellcheck", args: []string{"--version"}},
	"shfmt":             {name: "shfmt", scoop: "shfmt", executable: "shfmt", args: []string{"--version"}},
	"markdownlint-cli2": {name: "markdownlint-cli2", scoop: "markdownlint-cli2", executable: "markdownlint-cli2", args: []string{"--version"}},
	"gitleaks":          {name: "gitleaks", scoop: "gitleaks", executable: "gitleaks", args: []string{"version"}},
	"actionlint":        {name: "actionlint", scoop: "actionlint", executable: "actionlint", args: []string{"-version"}},
	"golangci-lint":     {name: "golangci-lint", executable: "golangci-lint", args: []string{"version"}},
	"task":              {name: "task", scoop: "task", executable: "task", args: []string{"--version"}},
	"just":              {name: "just", scoop: "just", executable: "just", args: []string{"--version"}},
	"make":              {name: "make", scoop: "make", executable: "make", args: []string{"--version"}},
	"pre-commit":        {name: "pre-commit", scoop: "pre-commit", executable: "pre-commit", args: []string{"--version"}},
	"jq":                {name: "jq", executable: "jq", args: []string{"--version"}},
	"yq":                {name: "yq", executable: "yq", args: []string{"--version"}},
}

func parseVersion(raw string) (version, error) {
	raw = strings.TrimSpace(strings.TrimPrefix(raw, "v"))
	parts := strings.Split(raw, ".")
	if len(parts) != 3 {
		return version{}, fmt.Errorf("version %q must contain major, minor, and patch components", raw)
	}
	values := [3]int{}
	for i, part := range parts {
		if part == "" {
			return version{}, fmt.Errorf("version %q contains an empty component", raw)
		}
		n, err := strconv.Atoi(part)
		if err != nil || n < 0 {
			return version{}, fmt.Errorf("version %q contains invalid numeric component", raw)
		}
		values[i] = n
	}
	return version{values[0], values[1], values[2]}, nil
}

func parseToolVersions(data string) ([]toolSpec, map[string]string, error) {
	versions := make(map[string]string)
	order := make([]toolSpec, 0)
	for lineNo, line := range strings.Split(strings.TrimPrefix(data, "\ufeff"), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		for idx, char := range line {
			if char == '#' && (idx == 0 || line[idx-1] == ' ' || line[idx-1] == '\t') {
				line = strings.TrimSpace(line[:idx])
				break
			}
		}
		fields := strings.Fields(line)
		if len(fields) != 2 {
			return nil, nil, fmt.Errorf("line %d: expected exactly tool and version", lineNo+1)
		}
		name, requested := fields[0], fields[1]
		if !toolNamePattern.MatchString(name) {
			return nil, nil, fmt.Errorf("line %d: invalid tool name %q", lineNo+1, name)
		}
		if _, exists := versions[name]; exists {
			return nil, nil, fmt.Errorf("line %d: duplicate tool entry %q", lineNo+1, name)
		}
		if !concreteVersionPattern.MatchString(requested) {
			return nil, nil, fmt.Errorf("line %d: tool %q has non-concrete version %q", lineNo+1, name, requested)
		}
		if _, err := parseVersion(requested); err != nil {
			return nil, nil, fmt.Errorf("line %d: tool %q: %w", lineNo+1, name, err)
		}
		versions[name] = strings.TrimPrefix(requested, "v")
		order = append(order, toolSpec{name: name})
	}
	if len(versions) == 0 {
		return nil, nil, errors.New("tool-version file contains no active entries")
	}
	return order, versions, nil
}

func validateMirror(canonical, mirror map[string]string) error {
	if len(canonical) != len(mirror) {
		return fmt.Errorf("mirror contains %d tools; canonical file contains %d", len(mirror), len(canonical))
	}
	for name, expected := range canonical {
		actual, ok := mirror[name]
		if !ok {
			return fmt.Errorf("mirror is missing tool %q", name)
		}
		ev, _ := parseVersion(expected)
		av, err := parseVersion(actual)
		if err != nil || ev != av {
			return fmt.Errorf("mirror version mismatch for %q: canonical %s, mirror %s", name, expected, actual)
		}
	}
	for name := range mirror {
		if _, ok := canonical[name]; !ok {
			return fmt.Errorf("mirror contains unexpected tool %q", name)
		}
	}
	return nil
}

func resolveRoot(override string) (string, error) {
	if override != "" {
		abs, err := filepath.Abs(override)
		if err != nil {
			return "", fmt.Errorf("resolve --root: %w", err)
		}
		return filepath.Clean(abs), nil
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
	seen := make(map[string]struct{}, len(candidates))
	for _, candidate := range candidates {
		candidate = filepath.Clean(candidate)
		if _, ok := seen[candidate]; ok {
			continue
		}
		seen[candidate] = struct{}{}
		for dir := candidate; ; dir = filepath.Dir(dir) {
			if fileExists(filepath.Join(dir, "tooling", ".tool-versions")) &&
				fileExists(filepath.Join(dir, "go.mod")) {
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
	cmd := exec.CommandContext(ctx, name, args...)
	var output bytes.Buffer
	cmd.Stdout = &output
	cmd.Stderr = &output
	err := cmd.Run()
	if err != nil {
		return output.String(), fmt.Errorf("%s %s: %w: %s", name, strings.Join(args, " "), err, strings.TrimSpace(output.String()))
	}
	return output.String(), nil
}

func findExecutable(name string) (string, error) {
	path, err := exec.LookPath(name)
	if err != nil {
		return "", fmt.Errorf("%s not found on PATH", name)
	}
	return path, nil
}

func findToolExecutable(spec toolSpec) (string, error) {
	path, err := findExecutable(spec.executable)
	if err == nil {
		return path, nil
	}
	if spec.name == "golangci-lint" {
		if home, homeErr := os.UserHomeDir(); homeErr == nil {
			candidate := filepath.Join(home, "bin", "golangci-lint.exe")
			if fileExists(candidate) {
				return candidate, nil
			}
		}
	}
	return "", err
}

func installedVersion(ctx context.Context, spec toolSpec, runner func(context.Context, string, ...string) (string, error)) (string, string, error) {
	exe, err := findToolExecutable(spec)
	if err != nil {
		return "", "", err
	}
	output, err := runner(ctx, exe, spec.args...)
	if err != nil {
		return exe, "", err
	}
	match := versionPattern.FindStringSubmatch(output)
	if match == nil {
		return exe, "", fmt.Errorf("could not parse version from %s output %q", spec.executable, strings.TrimSpace(output))
	}
	patch := "0"
	if match[3] != "" {
		patch = match[3]
	}
	v, err := parseVersion(match[1] + "." + match[2] + "." + patch)
	if err != nil {
		return exe, "", err
	}
	return exe, v.String(), nil
}

func existingGoVersionAllowed(requested, installed string) (bool, error) {
	required, err := parseVersion(requested)
	if err != nil {
		return false, fmt.Errorf("parse required Go version: %w", err)
	}
	actual, err := parseVersion(installed)
	if err != nil {
		return false, fmt.Errorf("parse installed Go version: %w", err)
	}
	if actual.major != required.major || actual.minor != required.minor || actual.patch < required.patch {
		return false, nil
	}
	return actual.patch-required.patch <= 9, nil
}

func pathContainsDirectory(value, directory string) bool {
	target := filepath.Clean(directory)
	for _, entry := range filepath.SplitList(value) {
		entry = strings.Trim(strings.TrimSpace(entry), `"`)
		if entry != "" && strings.EqualFold(filepath.Clean(entry), target) {
			return true
		}
	}
	return false
}

func scoopShimsDirectory(prefix string) string {
	for directory := filepath.Clean(prefix); ; {
		parent := filepath.Dir(directory)
		if strings.EqualFold(filepath.Base(directory), "apps") {
			return filepath.Join(parent, "shims")
		}
		if parent == directory {
			return ""
		}
		directory = parent
	}
}

func addUserToolDirectory(ctx context.Context, directory string) error {
	if !filepath.IsAbs(directory) || strings.ContainsAny(directory, ";\r\n") {
		return fmt.Errorf("invalid tool directory %q", directory)
	}
	info, err := os.Stat(directory)
	if err != nil {
		return fmt.Errorf("inspect tool directory %q: %w", directory, err)
	}
	if !info.IsDir() {
		return fmt.Errorf("tool path %q is not a directory", directory)
	}

	literal := "'" + strings.ReplaceAll(directory, "'", "''") + "'"
	script := `
$ErrorActionPreference = 'Stop'
$directory = ` + literal + `
$current = [Environment]::GetEnvironmentVariable('Path', 'User')
$found = $false
foreach ($entry in ($current -split ';')) {
    $entry = $entry.Trim().Trim('"')
    if (-not $entry) { continue }
    $entry = [Environment]::ExpandEnvironmentVariables($entry)
    if ([StringComparer]::OrdinalIgnoreCase.Equals(
        $entry.TrimEnd('\', '/'), $directory.TrimEnd('\', '/'))) {
        $found = $true
        break
    }
}
if (-not $found) {
    if ([string]::IsNullOrEmpty($current)) {
        $updated = $directory
    } elseif ($current.EndsWith(';')) {
        $updated = $current + $directory
    } else {
        $updated = $current + ';' + $directory
    }
    [Environment]::SetEnvironmentVariable('Path', $updated, 'User')
}
`
	if _, err := commandRunner(ctx, "powershell", "-Command", script); err != nil {
		return fmt.Errorf("persist tool directory %q in User PATH: %w", directory, err)
	}

	current := os.Getenv("PATH")
	if pathContainsDirectory(current, directory) {
		return nil
	}
	updated := directory
	if current != "" {
		updated += string(os.PathListSeparator) + current
	}
	if err := os.Setenv("PATH", updated); err != nil {
		return fmt.Errorf("update process PATH: %w", err)
	}
	fmt.Printf("added tool directory to process and User PATH: %s\n", directory)
	return nil
}

func repairToolPath(ctx context.Context, cfg config, spec toolSpec) error {
	switch spec.name {
	case "yamllint", "checkov":
	default:
		return nil
	}
	if cfg.dryRun {
		return nil
	}

	runner := cfg.commandFunc
	if runner == nil {
		runner = commandRunner
	}
	var candidates []string
	output, err := runner(ctx, "python", "-c",
		"import sysconfig; print(sysconfig.get_path('scripts')); "+
			"print(sysconfig.get_path('scripts', scheme='nt_user'))")
	if err == nil {
		candidates = append(candidates, strings.Split(output, "\n")...)
	} else if cfg.verbose {
		fmt.Fprintf(os.Stderr, "Python scripts discovery for %s: %v\n", spec.name, err)
	}

	if executable, err := findExecutable(spec.executable); err == nil {
		return addUserToolDirectory(ctx, filepath.Dir(executable))
	}
	for _, candidate := range candidates {
		directory := strings.TrimSpace(candidate)
		if filepath.IsAbs(directory) &&
			fileExists(filepath.Join(directory, spec.executable+".exe")) {
			return addUserToolDirectory(ctx, directory)
		}
	}

	// Ask Scoop for its actual installation prefix rather than guessing
	// SCOOP, SCOOP_GLOBAL, or version-specific installation directories.
	output, err = runner(ctx, "scoop", "prefix", spec.scoop)
	if err != nil {
		if cfg.verbose {
			fmt.Fprintf(os.Stderr, "%s Scoop prefix discovery: %v\n", spec.name, err)
		}
		return nil
	}
	prefix := strings.TrimSpace(output)
	if !filepath.IsAbs(prefix) {
		return nil
	}
	if shims := scoopShimsDirectory(prefix); shims != "" &&
		fileExists(filepath.Join(shims, spec.executable+".exe")) {
		return addUserToolDirectory(ctx, shims)
	}
	for _, directory := range []string{prefix, filepath.Join(prefix, "bin")} {
		if fileExists(filepath.Join(directory, spec.executable+".exe")) {
			return addUserToolDirectory(ctx, directory)
		}
	}
	return nil
}

func validateGoMod(root, required string) error {
	data, err := os.ReadFile(filepath.Join(root, "go.mod"))
	if err != nil {
		return fmt.Errorf("read go.mod: %w", err)
	}
	var declared string
	for lineNo, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(strings.TrimSpace(line))
		if len(fields) >= 2 && fields[0] == "go" {
			if declared != "" {
				return fmt.Errorf("go.mod contains duplicate go directives (line %d)", lineNo+1)
			}
			declared = fields[1]
		}
	}
	if declared == "" {
		return errors.New("go.mod does not contain a go directive")
	}
	requiredVersion, err := parseVersion(required)
	if err != nil {
		return fmt.Errorf("parse required golang version: %w", err)
	}
	declaredVersion, err := parseGoDirectiveVersion(declared)
	if err != nil {
		return fmt.Errorf("parse go.mod directive %q: %w", declared, err)
	}
	if requiredVersion.major != declaredVersion.major || requiredVersion.minor != declaredVersion.minor ||
		(declaredVersion.patch != 0 && requiredVersion.patch != declaredVersion.patch) {
		return fmt.Errorf("golang %s is incompatible with go.mod directive %s", required, declared)
	}
	return nil
}

func parseGoDirectiveVersion(raw string) (version, error) {
	parts := strings.Split(strings.TrimPrefix(strings.TrimSpace(raw), "v"), ".")
	if len(parts) == 2 {
		parts = append(parts, "0")
	}
	if len(parts) != 3 {
		return version{}, fmt.Errorf("expected major.minor or major.minor.patch")
	}
	return parseVersion(strings.Join(parts, "."))
}

func runScoop(ctx context.Context, args ...string) (string, error) {
	return commandRunner(ctx, "scoop", args...)
}

func ensureScoop(ctx context.Context, dryRun bool) error {
	path, err := findExecutable("scoop")
	if err != nil {
		if dryRun {
			fmt.Fprintln(os.Stderr, "dry-run: Scoop is not installed; installation would require manual Scoop bootstrap")
			return nil
		}
		return errors.New("missing Scoop installation; install it from the official Scoop documentationscoop.sh) and rerun")
	}
	if _, err := commandRunner(ctx, path, "--version"); err != nil {
		return fmt.Errorf("cannot use Scoop executable %q: %w", path, err)
	}
	addScoopShimsToPath()
	return nil
}

func addScoopShimsToPath() {
	scoopRoot := os.Getenv("SCOOP")
	if scoopRoot == "" {
		if home, err := os.UserHomeDir(); err == nil {
			scoopRoot = filepath.Join(home, "scoop")
		}
	}
	if scoopRoot == "" {
		return
	}
	shims := filepath.Join(scoopRoot, "shims")
	if info, err := os.Stat(shims); err != nil || !info.IsDir() {
		return
	}
	current := os.Getenv("PATH")
	for _, part := range strings.Split(current, string(os.PathListSeparator)) {
		if strings.EqualFold(filepath.Clean(part), filepath.Clean(shims)) {
			return
		}
	}
	_ = os.Setenv("PATH", shims+string(os.PathListSeparator)+current)
}

func updateScoop(ctx context.Context, dryRun bool) error {
	if dryRun {
		fmt.Fprintln(os.Stderr, "dry-run: would run 'scoop update'")
		return nil
	}
	if _, err := runScoop(ctx, "update"); err != nil {
		return fmt.Errorf("refresh Scoop metadata: %w", err)
	}
	return nil
}

func scoopInstall(ctx context.Context, spec toolSpec, requested string, force bool) error {
	packageRef := spec.scoop + "@" + requested
	args := []string{"install", packageRef}
	if force {
		args = append(args, "--force")
	}
	if _, err := runScoop(ctx, args...); err != nil {
		return fmt.Errorf("install %s %s with Scoop (exact package %s): %w", spec.name, requested, packageRef, err)
	}
	return nil
}

func architecture() (string, error) {
	switch runtime.GOARCH {
	case "amd64":
		return "amd64", nil
	case "arm64":
		return "arm64", nil
	default:
		return "", fmt.Errorf("unsupported Windows architecture %q; supported architectures are amd64 and arm64", runtime.GOARCH)
	}
}

func releaseURL(version, arch string) (string, string, error) {
	v, err := parseVersion(version)
	if err != nil {
		return "", "", err
	}
	tag := "v" + v.String()
	archive := fmt.Sprintf("golangci-lint-%s-windows-%s.zip", v.String(), arch)
	checksums := fmt.Sprintf("golangci-lint-%s-checksums.txt", v.String())
	base := "https://github.com/golangci/golangci-lint/releases/download/" + tag + "/"
	archiveURL := base + url.PathEscape(archive)
	checksumURL := base + url.PathEscape(checksums)
	for _, raw := range []string{archiveURL, checksumURL} {
		parsed, parseErr := url.Parse(raw)
		if parseErr != nil || parsed.Scheme != "https" || parsed.Host != "github.com" {
			return "", "", fmt.Errorf("refusing unsafe release URL %q", raw)
		}
	}
	return archiveURL, checksumURL, nil
}

func download(ctx context.Context, client *http.Client, rawURL string, limit int64) ([]byte, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil || parsed.Scheme != "https" || parsed.Host == "" {
		return nil, fmt.Errorf("refusing non-HTTPS URL %q", rawURL)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, parsed.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("create download request: %w", err)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("download %s: %w", rawURL, err)
	}
	defer func() {
		if err := resp.Body.Close(); err != nil {
			fmt.Fprintf(os.Stderr, "warning: close download response body for %s: %v\n", rawURL, err)
		}
	}()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("download %s returned HTTP %s", rawURL, resp.Status)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, limit+1))
	if err != nil {
		return nil, fmt.Errorf("read download %s: %w", rawURL, err)
	}
	if int64(len(body)) > limit {
		return nil, fmt.Errorf("download %s exceeds %d-byte limit", rawURL, limit)
	}
	return body, nil
}

func defaultHTTPClient(timeout time.Duration) *http.Client {
	return &http.Client{
		Timeout: timeout,
		CheckRedirect: func(req *http.Request, _ []*http.Request) error {
			if req.URL.Scheme != "https" {
				return errors.New("refusing redirect to non-HTTPS URL")
			}
			switch strings.ToLower(req.URL.Hostname()) {
			case "github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com":
				return nil
			default:
				return fmt.Errorf("refusing redirect to untrusted host %q", req.URL.Host)
			}
		},
	}
}

func parseChecksums(data []byte, expectedFile string) (string, error) {
	lines := strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n")
	checksums := make(map[string]string)
	for lineNo, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		fields := strings.Fields(line)
		if len(fields) != 2 || len(fields[0]) != 64 {
			return "", fmt.Errorf("malformed checksum entry on line %d", lineNo+1)
		}
		if _, err := hex.DecodeString(fields[0]); err != nil {
			return "", fmt.Errorf("invalid SHA-256 checksum on line %d: %w", lineNo+1, err)
		}
		name := strings.TrimPrefix(fields[1], "*")
		if _, exists := checksums[name]; exists {
			return "", fmt.Errorf("duplicate checksum entry for %q", name)
		}
		checksums[name] = strings.ToLower(fields[0])
	}
	checksum, ok := checksums[expectedFile]
	if !ok {
		return "", fmt.Errorf("checksum manifest does not contain expected artifact %q", expectedFile)
	}
	return checksum, nil
}

// parseChecksumsBSD parses a BSD-style checksum manifest of the form:
//
//	SHA256 (filename) = <64-char hex>
//
// It returns the lower-case SHA-256 digest for expectedFile.
func parseChecksumsBSD(data []byte, expectedFile string) (string, error) {
	lines := strings.Split(strings.ReplaceAll(string(data), "\r\n", "\n"), "\n")
	for lineNo, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		// Accept only SHA-256 entries; skip MD5, SHA-1, etc.
		const algoPrefix = "SHA256 ("
		if !strings.HasPrefix(strings.ToUpper(line), strings.ToUpper(algoPrefix)) {
			continue
		}
		rest := line[len(algoPrefix):]
		idx := strings.Index(rest, ") = ")
		if idx < 0 {
			return "", fmt.Errorf("malformed BSD checksum entry on line %d", lineNo+1)
		}
		filename := rest[:idx]
		hash := strings.TrimSpace(rest[idx+4:])
		if len(hash) != 64 {
			return "", fmt.Errorf("unexpected hash length on line %d: want 64, got %d", lineNo+1, len(hash))
		}
		if _, err := hex.DecodeString(hash); err != nil {
			return "", fmt.Errorf("invalid hex on line %d: %w", lineNo+1, err)
		}
		if filename == expectedFile {
			return strings.ToLower(hash), nil
		}
	}
	return "", fmt.Errorf("no SHA-256 checksum found for %q in checksums-bsd file", expectedFile)
}

func safeArchiveFile(name string) error {
	if name == "" || filepath.IsAbs(name) || filepath.VolumeName(name) != "" ||
		strings.HasPrefix(name, "/") || strings.HasPrefix(name, `\`) {
		return errors.New("archive contains an absolute or volume-qualified path")
	}
	clean := filepath.Clean(filepath.FromSlash(name))
	if clean == "." || clean == ".." || strings.HasPrefix(clean, ".."+string(filepath.Separator)) {
		return fmt.Errorf("archive path traversal detected for %q", name)
	}
	for _, part := range strings.FieldsFunc(name, func(r rune) bool { return r == '/' || r == '\\' }) {
		if part == ".." {
			return fmt.Errorf("archive path traversal detected for %q", name)
		}
	}
	return nil
}

func installGolangCILint(ctx context.Context, cfg config, requested string) error {
	arch, err := architecture()
	if err != nil {
		return err
	}
	archiveURL, checksumURL, err := releaseURL(requested, arch)
	if err != nil {
		return fmt.Errorf("construct golangci-lint release URL: %w", err)
	}
	archiveName := path.Base(archiveURL)
	if cfg.dryRun {
		fmt.Printf("dry-run: would download and verify golangci-lint %s (%s) from %s\n", requested, arch, archiveURL)
		return nil
	}
	client := cfg.httpClient
	if client == nil {
		client = defaultHTTPClient(cfg.timeout)
	}
	archiveData, err := download(ctx, client, archiveURL, maxDownloadSize)
	if err != nil {
		return err
	}
	checksumData, err := download(ctx, client, checksumURL, maxChecksumSize)
	if err != nil {
		return err
	}
	expected, err := parseChecksums(checksumData, archiveName)
	if err != nil {
		return err
	}
	actualBytes := sha256.Sum256(archiveData)
	actual := hex.EncodeToString(actualBytes[:])
	if !strings.EqualFold(actual, expected) {
		return fmt.Errorf("golangci-lint checksum mismatch: expected %s, got %s", expected, actual)
	}
	zr, err := zip.NewReader(bytes.NewReader(archiveData), int64(len(archiveData)))
	if err != nil {
		return fmt.Errorf("open golangci-lint archive: %w", err)
	}
	var executable []byte
	for _, file := range zr.File {
		if err := safeArchiveFile(file.Name); err != nil {
			return err
		}
		if file.FileInfo().IsDir() {
			continue
		}
		if file.Mode()&os.ModeSymlink != 0 {
			return fmt.Errorf("archive contains a symlink entry %q", file.Name)
		}
		if filepath.Base(filepath.FromSlash(file.Name)) != "golangci-lint.exe" {
			continue
		}
		if executable != nil {
			return errors.New("archive contains multiple golangci-lint.exe files")
		}
		if file.UncompressedSize64 > maxDownloadSize {
			return errors.New("golangci-lint executable exceeds size limit")
		}
		rc, openErr := file.Open()
		if openErr != nil {
			return fmt.Errorf("open executable in archive: %w", openErr)
		}
		executable, err = io.ReadAll(io.LimitReader(rc, maxDownloadSize+1))
		closeErr := rc.Close()
		if closeErr != nil {
			closeErr = fmt.Errorf("close executable in archive: %w", closeErr)
		}
		if err != nil {
			return errors.Join(fmt.Errorf("read executable from archive: %w", err), closeErr)
		}
		if closeErr != nil {
			return closeErr
		}
		if int64(len(executable)) > maxDownloadSize {
			return errors.New("golangci-lint executable exceeds size limit")
		}
	}
	if len(executable) == 0 {
		return errors.New("archive does not contain golangci-lint.exe")
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("resolve user home directory: %w", err)
	}
	destDir := filepath.Join(home, "bin")
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return fmt.Errorf("create user tool directory %q: %w", destDir, err)
	}
	dest := filepath.Join(destDir, "golangci-lint.exe")
	tmp, err := os.CreateTemp(destDir, ".golangci-lint-*.tmp")
	if err != nil {
		return fmt.Errorf("create temporary installation file: %w", err)
	}
	tmpName := tmp.Name()
	defer func() {
		if err := os.Remove(tmpName); err != nil && !errors.Is(err, os.ErrNotExist) {
			fmt.Fprintf(os.Stderr, "warning: remove temporary installation file %q: %v\n", tmpName, err)
		}
	}()
	if _, err := tmp.Write(executable); err != nil {
		writeErr := fmt.Errorf("write temporary installation file: %w", err)
		if closeErr := tmp.Close(); closeErr != nil {
			return errors.Join(writeErr, fmt.Errorf("close temporary installation file: %w", closeErr))
		}
		return writeErr
	}
	if err := tmp.Chmod(0o755); err != nil {
		chmodErr := fmt.Errorf("set temporary installation permissions: %w", err)
		if closeErr := tmp.Close(); closeErr != nil {
			return errors.Join(chmodErr, fmt.Errorf("close temporary installation file: %w", closeErr))
		}
		return chmodErr
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("close temporary installation file: %w", err)
	}
	if err := tmp.Close(); err != nil {
		return fmt.Errorf("close temporary installation file: %w", err)
	}
	backup := ""
	if _, statErr := os.Stat(dest); statErr == nil {
		backup = dest + ".backup-" + strconv.FormatInt(time.Now().UnixNano(), 10)
		if err := os.Rename(dest, backup); err != nil {
			return fmt.Errorf("stage existing golangci-lint for replacement: %w", err)
		}
	} else if !os.IsNotExist(statErr) {
		return fmt.Errorf("inspect existing golangci-lint installation: %w", statErr)
	}
	if err := os.Rename(tmpName, dest); err != nil {
		if backup != "" {
			_ = os.Rename(backup, dest)
		}
		return fmt.Errorf("atomically install golangci-lint: %w", err)
	}
	if backup != "" {
		_ = os.Remove(backup)
	}
	currentPath := os.Getenv("PATH")
	if !strings.Contains(strings.ToLower(string(os.PathSeparator)+currentPath+string(os.PathSeparator)),
		strings.ToLower(string(os.PathSeparator)+destDir+string(os.PathSeparator))) {
		_ = os.Setenv("PATH", destDir+string(os.PathListSeparator)+currentPath)
		fmt.Fprintf(os.Stderr, "golangci-lint installed in %s; add this directory to your user PATH for new shells\n", destDir)
	}
	return nil
}

// jqReleaseURL constructs the download and checksum URLs for a jq release.
func jqReleaseURL(ver, arch string) (string, string, error) {
	v, err := parseVersion(ver)
	if err != nil {
		return "", "", err
	}
	tag := "jq-" + v.String()
	var archName string
	switch arch {
	case "amd64":
		archName = "jq-windows-amd64.exe"
	case "arm64":
		archName = "jq-windows-arm64.exe"
	default:
		return "", "", fmt.Errorf("unsupported architecture %q for jq", arch)
	}
	base := "https://github.com/jqlang/jq/releases/download/" + url.PathEscape(tag) + "/"
	binaryURL := base + archName
	checksumURL := base + "sha256sum.txt"
	for _, raw := range []string{binaryURL, checksumURL} {
		parsed, parseErr := url.Parse(raw)
		if parseErr != nil || parsed.Scheme != "https" || parsed.Host != "github.com" {
			return "", "", fmt.Errorf("refusing unsafe jq release URL %q", raw)
		}
	}
	return binaryURL, checksumURL, nil
}

// yqReleaseURL constructs the download and checksum URLs for a yq release.
func yqReleaseURL(ver, arch string) (string, string, error) {
	v, err := parseVersion(ver)
	if err != nil {
		return "", "", err
	}
	tag := "v" + v.String()
	var archName string
	switch arch {
	case "amd64":
		archName = "yq_windows_amd64.exe"
	case "arm64":
		archName = "yq_windows_arm64.exe"
	default:
		return "", "", fmt.Errorf("unsupported architecture %q for yq", arch)
	}
	base := "https://github.com/mikefarah/yq/releases/download/" + url.PathEscape(tag) + "/"
	binaryURL := base + archName
	checksumURL := base + "checksums-bsd"
	for _, raw := range []string{binaryURL, checksumURL} {
		parsed, parseErr := url.Parse(raw)
		if parseErr != nil || parsed.Scheme != "https" || parsed.Host != "github.com" {
			return "", "", fmt.Errorf("refusing unsafe yq release URL %q", raw)
		}
	}
	return binaryURL, checksumURL, nil
}

// installBinaryTool downloads, checksum-verifies, and installs a single-binary
// tool (jq or yq) directly from GitHub Releases into ~/bin, bypassing Scoop.
// checksumParser extracts the expected hex digest from the checksum file bytes.
func installBinaryTool(
	ctx context.Context,
	cfg config,
	toolName, requested, exeName string,
	binaryURL, checksumURL string,
	checksumParser func([]byte, string) (string, error),
) error {
	if cfg.dryRun {
		fmt.Printf("dry-run: would download and verify %s %s from %s\n", toolName, requested, binaryURL)
		return nil
	}
	client := cfg.httpClient
	if client == nil {
		client = defaultHTTPClient(cfg.timeout)
	}
	binaryData, err := download(ctx, client, binaryURL, maxDownloadSize)
	if err != nil {
		return fmt.Errorf("download %s binary: %w", toolName, err)
	}
	checksumData, err := download(ctx, client, checksumURL, maxChecksumSize)
	if err != nil {
		return fmt.Errorf("download %s checksum: %w", toolName, err)
	}
	expected, err := checksumParser(checksumData, path.Base(binaryURL))
	if err != nil {
		return fmt.Errorf("parse %s checksum: %w", toolName, err)
	}
	actualBytes := sha256.Sum256(binaryData)
	actual := hex.EncodeToString(actualBytes[:])
	if !strings.EqualFold(actual, expected) {
		return fmt.Errorf("%s checksum mismatch: expected %s, got %s", toolName, expected, actual)
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return fmt.Errorf("resolve home directory for %s: %w", toolName, err)
	}
	destDir := filepath.Join(home, "bin")
	if err := os.MkdirAll(destDir, 0o755); err != nil {
		return fmt.Errorf("create tool directory for %s: %w", toolName, err)
	}
	dest := filepath.Join(destDir, exeName)
	tmp, err := os.CreateTemp(destDir, "."+toolName+"-*.tmp")
	if err != nil {
		return fmt.Errorf("create temporary file for %s: %w", toolName, err)
	}
	tmpName := tmp.Name()
	defer func() {
		if removeErr := os.Remove(tmpName); removeErr != nil && !errors.Is(removeErr, os.ErrNotExist) {
			fmt.Fprintf(os.Stderr, "warning: remove temporary file %q: %v\n", tmpName, removeErr)
		}
	}()
	if _, writeErr := tmp.Write(binaryData); writeErr != nil {
		_ = tmp.Close()
		return fmt.Errorf("write %s binary: %w", toolName, writeErr)
	}
	if chmodErr := tmp.Chmod(0o755); chmodErr != nil {
		_ = tmp.Close()
		return fmt.Errorf("set permissions for %s: %w", toolName, chmodErr)
	}
	if closeErr := tmp.Close(); closeErr != nil {
		return fmt.Errorf("close temporary file for %s: %w", toolName, closeErr)
	}
	if renameErr := os.Rename(tmpName, dest); renameErr != nil {
		return fmt.Errorf("install %s to %s: %w", toolName, dest, renameErr)
	}
	currentPath := os.Getenv("PATH")
	if !pathContainsDirectory(currentPath, destDir) {
		_ = os.Setenv("PATH", destDir+string(os.PathListSeparator)+currentPath)
		fmt.Fprintf(os.Stderr, "%s installed in %s; add this directory to your user PATH for new shells\n", toolName, destDir)
	}
	return nil
}

func installJQ(ctx context.Context, cfg config, requested string) error {
	arch, err := architecture()
	if err != nil {
		return err
	}
	binaryURL, checksumURL, err := jqReleaseURL(requested, arch)
	if err != nil {
		return fmt.Errorf("construct jq release URL: %w", err)
	}
	return installBinaryTool(ctx, cfg, "jq", requested, "jq.exe",
		binaryURL, checksumURL, parseChecksums)
}

func installYQ(ctx context.Context, cfg config, requested string) error {
	arch, err := architecture()
	if err != nil {
		return err
	}
	binaryURL, checksumURL, err := yqReleaseURL(requested, arch)
	if err != nil {
		return fmt.Errorf("construct yq release URL: %w", err)
	}
	return installBinaryTool(ctx, cfg, "yq", requested, "yq.exe",
		binaryURL, checksumURL, parseChecksumsBSD)
}

func installPipTool(ctx context.Context, cfg config, toolName, requested string) error {
	pkg := toolName + "==" + requested
	if cfg.dryRun {
		fmt.Printf("dry-run: would run python -m pip install --user %s\n", pkg)
		return nil
	}
	runner := cfg.commandFunc
	if runner == nil {
		runner = commandRunner
	}
	if _, err := runner(ctx, "python", "-m", "pip", "install", "--user", pkg); err != nil {
		return fmt.Errorf("pip install --user %s: %w", pkg, err)
	}
	return nil
}

func installYamllint(ctx context.Context, cfg config, requested string) error {
	return installPipTool(ctx, cfg, "yamllint", requested)
}

func installCheckov(ctx context.Context, cfg config, requested string) error {
	return installPipTool(ctx, cfg, "checkov", requested)
}

type installerFn func(context.Context, config, string) error

var directInstallers = map[string]installerFn{
	"golangci-lint": installGolangCILint,
	"jq":            installJQ,
	"yq":            installYQ,
	"yamllint":      installYamllint,
	"checkov":       installCheckov,
}

func processTool(ctx context.Context, cfg config, requested string, spec toolSpec) toolResult {
	result := toolResult{name: spec.name, version: requested}
	runner := cfg.commandFunc
	if runner == nil {
		runner = commandRunner
	}
	if err := repairToolPath(ctx, cfg, spec); err != nil {
		result.status, result.err = "failed", err
		return result
	}
	if exe, current, err := installedVersion(ctx, spec, runner); err == nil {
		if !cfg.force {
			if current == requested {
				result.status = "already-satisfied"
				fmt.Printf("%s %s already satisfied (%s)\n", spec.name, requested, exe)
				return result
			}
			if spec.name == "golang" {
				allowed, allowedErr := existingGoVersionAllowed(requested, current)
				if allowedErr != nil {
					result.status, result.err = "failed", allowedErr
					return result
				}
				if allowed {
					result.status = "already-satisfied"
					fmt.Printf("%s %s already satisfied by existing %s (%s)\n", spec.name, requested, current, exe)
					return result
				}
			}
		}
		fmt.Printf("%s installed at %s; required %s\n", spec.name, current, requested)
	} else if cfg.verbose {
		fmt.Fprintf(os.Stderr, "%s is not currently usable: %v\n", spec.name, err)
	}
	if installer, ok := directInstallers[spec.name]; ok {
		if err := installer(ctx, cfg, requested); err != nil {
			result.status, result.err = "failed", err
			return result
		}
		result.checksumVerified = !cfg.dryRun
	} else {
		if cfg.dryRun {
			fmt.Printf("dry-run: would install %s %s via Scoop package %s@%s\n", spec.name, requested, spec.scoop, requested)
			result.status = "would-install"
			return result
		}
		if err := scoopInstall(ctx, spec, requested, cfg.force); err != nil {
			result.status, result.err = "failed", err
			return result
		}
	}
	if cfg.dryRun {
		result.status = "would-install"
		return result
	}
	if err := repairToolPath(ctx, cfg, spec); err != nil {
		result.status, result.verifyFailure, result.err = "failed", true,
			fmt.Errorf("post-install PATH repair for %s: %w", spec.name, err)
		return result
	}
	if exe, current, err := installedVersion(ctx, spec, runner); err != nil {
		result.status, result.verifyFailure, result.err = "failed", true, fmt.Errorf("post-install verification for %s: %w", spec.name, err)
	} else if current != requested {
		result.status, result.verifyFailure, result.err = "failed", true, fmt.Errorf("post-install version mismatch for %s: expected %s, got %s (%s)", spec.name, requested, current, exe)
	} else {
		result.status = "installed"
		fmt.Printf("%s %s installed and verified (%s)\n", spec.name, requested, exe)
	}
	return result
}

func run(cfg config) int {
	if runtime.GOOS != "windows" {
		fmt.Fprintf(os.Stderr, "unsupported operating system %q: this installer is Windows-only\n", runtime.GOOS)
		return exitUnsupported
	}
	root, err := resolveRoot(cfg.root)
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: %v\n", err)
		return exitValidation
	}
	cfg.root = root
	fmt.Printf("repository root: %s\n", root)
	canonicalData, err := os.ReadFile(filepath.Join(root, "tooling", ".tool-versions"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: read canonical .tool-versions: %v\n", err)
		return exitValidation
	}
	order, versions, err := parseToolVersions(string(canonicalData))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: parse canonical .tool-versions: %v\n", err)
		return exitValidation
	}
	mirrorData, err := os.ReadFile(filepath.Join(root, "tooling", "cross-platform", "asdf-tool-versions"))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: read mirror asdf-tool-versions: %v\n", err)
		return exitValidation
	}
	_, mirror, err := parseToolVersions(string(mirrorData))
	if err != nil {
		fmt.Fprintf(os.Stderr, "validation error: parse mirror asdf-tool-versions: %v\n", err)
		return exitValidation
	}
	if err := validateMirror(versions, mirror); err != nil {
		fmt.Fprintf(os.Stderr, "validation error: %v\n", err)
		return exitValidation
	}
	if golang, ok := versions["golang"]; !ok {
		fmt.Fprintln(os.Stderr, "validation error: canonical .tool-versions is missing golang")
		return exitValidation
	} else if err := validateGoMod(root, golang); err != nil {
		fmt.Fprintf(os.Stderr, "validation error: %v\n", err)
		return exitValidation
	}
	signalCtx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	ctx, cancel := context.WithTimeout(signalCtx, cfg.timeout)
	defer cancel()
	if err := ensureScoop(ctx, cfg.dryRun); err != nil {
		fmt.Fprintf(os.Stderr, "Scoop error: %v\n", err)
		return exitInstall
	}
	if err := updateScoop(ctx, cfg.dryRun); err != nil {
		fmt.Fprintf(os.Stderr, "Scoop error: %v\n", err)
		return exitInstall
	}
	results := make([]toolResult, 0, len(order))
	for _, entry := range order {
		requested := versions[entry.name]
		spec, ok := toolSpecs[entry.name]
		if !ok {
			results = append(results, toolResult{name: entry.name, version: requested, status: "failed", err: errors.New("no supported Windows installation mapping")})
			continue
		}
		results = append(results, processTool(ctx, cfg, requested, spec))
	}
	fmt.Println("\nInstallation summary:")
	failed := 0
	verificationFailures := 0
	checksumsVerified := 0
	for _, result := range results {
		if result.err != nil {
			failed++
			if result.verifyFailure {
				verificationFailures++
			}
			fmt.Printf("  %-20s %-16s FAILED: %v\n", result.name, result.version, result.err)
		} else {
			fmt.Printf("  %-20s %-16s %s\n", result.name, result.version, result.status)
		}
		if result.checksumVerified {
			checksumsVerified++
		}
	}
	if failed > 0 {
		if errors.Is(ctx.Err(), context.Canceled) {
			return exitInterrupted
		}
		if verificationFailures > 0 {
			return exitVerify
		}
		return exitInstall
	}
	fmt.Printf("  checksum verification: %d downloaded artifact(s) verified\n", checksumsVerified)
	if errors.Is(ctx.Err(), context.Canceled) {
		return exitInterrupted
	}
	if errors.Is(ctx.Err(), context.DeadlineExceeded) {
		return exitInstall
	}
	return exitOK
}

func main() {
	flags := flag.NewFlagSet(os.Args[0], flag.ContinueOnError)
	flags.SetOutput(os.Stderr)
	root := flags.String("root", "", "repository root (defaults to discovery from the working directory)")
	dryRun := flags.Bool("dry-run", false, "validate and show intended actions without changing the system")
	verbose := flags.Bool("verbose", false, "enable verbose diagnostics")
	force := flags.Bool("force", false, "reinstall tools even when the required version is already present")
	timeout := flags.Duration("timeout", 10*time.Minute, "overall operation timeout")
	if err := flags.Parse(os.Args[1:]); err != nil {
		os.Exit(exitValidation)
	}
	if *timeout <= 0 {
		fmt.Fprintln(os.Stderr, "validation error: --timeout must be positive")
		os.Exit(exitValidation)
	}
	cfg := config{
		root:       *root,
		dryRun:     *dryRun,
		verbose:    *verbose,
		force:      *force,
		timeout:    *timeout,
		httpClient: defaultHTTPClient(*timeout),
	}
	code := run(cfg)
	os.Exit(code)
}
