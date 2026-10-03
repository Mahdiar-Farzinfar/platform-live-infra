// Command detect-changed-stacks prints the affected Terragrunt stack directories.
//
// Examples:
//
//	go run ./scripts/ci/detect-changed-stacks.go --base origin/main
//	go run ./scripts/ci/detect-changed-stacks.go --files-from changes.txt
//	git diff --name-only -z BASE HEAD | go run ./scripts/ci/detect-changed-stacks.go --files-from - --null
//
// stdout is always one JSON object: {"stacks":["live/..."]}. Paths are sorted,
// repository relative, and use forward slashes. Errors go to stderr only.
package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
)

func main() {
	if err := run(os.Args[1:], os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, "detect-changed-stacks:", err)
		os.Exit(1)
	}
}

func run(args []string, stdin io.Reader, stdout io.Writer) error {
	f := flag.NewFlagSet("detect-changed-stacks", flag.ContinueOnError)
	f.SetOutput(os.Stderr)
	f.Usage = func() {
		fmt.Fprintln(f.Output(), "Usage: detect-changed-stacks [--root DIR] (--base REF [--head REF] | --files-from FILE [--null])")
		fmt.Fprintln(f.Output(), "Compare two Git revisions, or read repository-relative changed paths from FILE (- for stdin).")
		fmt.Fprintln(f.Output(), "Git mode includes both old and new names for renames; files mode expects one path per line or NUL-delimited paths with --null.")
		fmt.Fprintln(f.Output(), "Shared live configuration, policies, and inventory changes select all discovered stacks.")
		fmt.Fprintln(f.Output(), "Output: JSON object with a sorted 'stacks' array of repository-relative directories; no changes yields [].")
		f.PrintDefaults()
	}
	rootFlag := f.String("root", "", "repository root (defaults to the root containing this source file)")
	base := f.String("base", "", "Git diff base revision (required in Git mode)")
	head := f.String("head", "HEAD", "Git diff head revision")
	filesFrom := f.String("files-from", "", "read changed paths from a file, or - for stdin")
	nul := f.Bool("null", false, "read NUL-delimited paths with --files-from")
	if err := f.Parse(args); err != nil {
		return err
	}
	if f.NArg() != 0 {
		return fmt.Errorf("unexpected positional arguments: %q", f.Args())
	}
	if (*base == "") == (*filesFrom == "") {
		return errors.New("specify exactly one of --base or --files-from")
	}
	if *filesFrom != "" && *head != "HEAD" {
		return errors.New("--head requires --base")
	}
	if *nul && *filesFrom == "" {
		return errors.New("--null requires --files-from")
	}
	if strings.TrimSpace(*base) != *base || strings.TrimSpace(*head) != *head || *head == "" {
		return errors.New("Git revisions must be nonempty and have no surrounding whitespace")
	}
	root, err := resolveRoot(*rootFlag)
	if err != nil {
		return err
	}
	stacks, err := discoverStacks(root)
	if err != nil {
		return err
	}
	var changed []string
	if *base != "" {
		changed, err = gitChanges(root, *base, *head)
	} else {
		changed, err = readChanges(*filesFrom, *nul, stdin)
	}
	if err != nil {
		return err
	}
	affected, err := affectedStacks(changed, stacks)
	if err != nil {
		return err
	}
	return json.NewEncoder(stdout).Encode(struct {
		Stacks []string `json:"stacks"`
	}{affected})
}

func resolveRoot(override string) (string, error) {
	root := override
	if root == "" {
		_, source, _, ok := runtime.Caller(0)
		if !ok || !filepath.IsAbs(source) {
			return "", errors.New("cannot locate source file; pass --root explicitly")
		}
		root = filepath.Join(filepath.Dir(source), "..", "..")
	}
	var err error
	root, err = filepath.Abs(root)
	if err != nil {
		return "", fmt.Errorf("resolve repository root: %w", err)
	}
	root, err = filepath.EvalSymlinks(root)
	if err != nil {
		return "", fmt.Errorf("resolve repository root %q: %w", root, err)
	}
	for _, name := range []string{"go.mod", "live"} {
		if _, err := os.Stat(filepath.Join(root, name)); err != nil {
			return "", fmt.Errorf("invalid repository root %q: %s: %w", root, name, err)
		}
	}
	return root, nil
}

func discoverStacks(root string) ([]string, error) {
	var stacks []string
	err := filepath.WalkDir(filepath.Join(root, "live"), func(name string, entry fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if entry.IsDir() && (entry.Name() == ".terragrunt-cache" || entry.Name() == ".terraform") {
			return filepath.SkipDir
		}
		if entry.IsDir() || entry.Name() != "terragrunt.hcl" {
			return nil
		}
		rel, err := filepath.Rel(root, filepath.Dir(name))
		if err != nil {
			return err
		}
		rel = filepath.ToSlash(rel)
		if rel != "live" {
			stacks = append(stacks, rel)
		}
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("discover Terragrunt stacks: %w", err)
	}
	sort.Strings(stacks)
	for i, stack := range stacks {
		if i > 0 && strings.HasPrefix(stack, stacks[i-1]+"/") {
			return nil, fmt.Errorf("nested Terragrunt stacks %q and %q are ambiguous", stacks[i-1], stack)
		}
	}
	return stacks, nil
}

func gitChanges(root, base, head string) ([]string, error) {
	// --end-of-options prevents refs beginning with '-' from becoming Git flags.
	cmd := exec.Command("git", "-C", root, "diff", "--no-ext-diff", "--name-status", "-z", "--find-renames", "--end-of-options", base, head)
	out, err := cmd.Output()
	if err != nil {
		var exit *exec.ExitError
		if errors.As(err, &exit) {
			return nil, fmt.Errorf("git diff %q %q failed: %s", base, head, strings.TrimSpace(string(exit.Stderr)))
		}
		return nil, fmt.Errorf("run git diff (is Git installed?): %w", err)
	}
	if len(out) == 0 {
		return []string{}, nil
	}
	parts := bytes.Split(out, []byte{0})
	if len(parts[len(parts)-1]) != 0 {
		return nil, errors.New("malformed NUL-delimited Git diff output")
	}
	parts = parts[:len(parts)-1]
	var changed []string
	for i := 0; i < len(parts); {
		status := string(parts[i])
		i++
		count := 1
		if strings.HasPrefix(status, "R") || strings.HasPrefix(status, "C") {
			count = 2
		} else if len(status) != 1 || !strings.Contains("ADM TUXB", status) || status == " " {
			return nil, fmt.Errorf("unexpected Git change status %q", status)
		}
		if i+count > len(parts) {
			return nil, fmt.Errorf("missing path for Git change status %q", status)
		}
		for _, p := range parts[i : i+count] {
			changed = append(changed, string(p))
		}
		i += count
	}
	return changed, nil
}

func readChanges(source string, nul bool, stdin io.Reader) ([]string, error) {
	r := stdin
	if source != "-" {
		file, err := os.Open(source)
		if err != nil {
			return nil, fmt.Errorf("open changed-files source %q: %w", source, err)
		}
		defer file.Close()
		r = file
	}
	if nul {
		data, err := io.ReadAll(r)
		if err != nil {
			return nil, fmt.Errorf("read changed-files source: %w", err)
		}
		if len(data) == 0 {
			return []string{}, nil
		}
		if data[len(data)-1] != 0 {
			return nil, errors.New("--null input must end with a NUL byte")
		}
		parts := bytes.Split(data[:len(data)-1], []byte{0})
		files := make([]string, 0, len(parts))
		for _, part := range parts {
			files = append(files, string(part))
		}
		return files, nil
	}
	var files []string
	scanner := bufio.NewScanner(r)
	scanner.Buffer(make([]byte, 4096), 1024*1024)
	for scanner.Scan() {
		files = append(files, strings.TrimSuffix(scanner.Text(), "\r"))
	}
	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("read changed-files source: %w", err)
	}
	return files, nil
}

func normalizePath(p string) (string, error) {
	if p == "" || strings.ContainsAny(p, "\x00\r\n") {
		return "", fmt.Errorf("invalid empty or control-character path %q", p)
	}
	p = strings.ReplaceAll(p, `\`, "/")
	if strings.HasPrefix(p, "/") || strings.Contains(p, ":") || path.Clean(p) != p || p == "." || p == ".." || strings.HasPrefix(p, "../") {
		return "", fmt.Errorf("expected a normalized repository-relative path, got %q", p)
	}
	return p, nil
}

func affectedStacks(changed, stacks []string) ([]string, error) {
	selected := make(map[string]bool)
	all := false
	for _, raw := range changed {
		p, err := normalizePath(raw)
		if err != nil {
			return nil, err
		}
		if p == "live/terragrunt.hcl" || p == "live/common.hcl" || strings.HasPrefix(p, "live/catalogs/") || strings.HasPrefix(p, "live/_envcommon/") || strings.HasPrefix(p, "inventory/") || strings.HasPrefix(p, "policies/") {
			all = true
			continue
		}
		if !strings.HasPrefix(p, "live/") {
			continue
		}
		if path.Base(p) == "terragrunt.hcl" {
			found := false
			for _, stack := range stacks {
				if path.Dir(p) == stack {
					found = true
					break
				}
			}
			if !found {
				return nil, fmt.Errorf("changed stack definition %q has no deployable stack in the current live tree", p)
			}
		}
		for _, stack := range stacks {
			if strings.HasPrefix(p, stack+"/") {
				selected[stack] = true
			} else if strings.HasPrefix(stack, p+"/") || strings.HasPrefix(stack, path.Dir(p)+"/") {
				// Account and region configuration affects every descendant stack.
				selected[stack] = true
			}
		}
	}
	result := make([]string, 0, len(stacks))
	for _, stack := range stacks {
		if all || selected[stack] {
			result = append(result, stack)
		}
	}
	return result, nil
}
