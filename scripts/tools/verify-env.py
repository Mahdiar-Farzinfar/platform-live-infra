#!/usr/bin/env python3
"""Verify the repository's pinned development environment.

This command is intentionally read-only. It never installs tools, modifies PATH,
changes files, invokes a shell, or mutates package-manager state.

Exit codes:
    0   All validations and tool checks passed.
    2   Repository or configuration validation failed.
    3   One or more required tools are missing, unusable, or have a wrong version.
    4   Host platform or architecture is unsupported.
    130 Interrupted by the user.
    99  Unexpected verifier failure.
"""

from __future__ import annotations

import argparse
import json
import os
import platform as host_platform
import sysconfig
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional


EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_ENVIRONMENT = 3
EXIT_PLATFORM = 4
EXIT_INTERRUPTED = 130
EXIT_UNEXPECTED = 99

DEFAULT_TIMEOUT_SECONDS = 10.0

TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
CONCRETE_VERSION_RE = re.compile(
    r"^v?(?P<major>[0-9]+)\."
    r"(?P<minor>[0-9]+)\."
    r"(?P<patch>[0-9]+)$"
)
VERSION_RE = re.compile(
    r"(?<![0-9])v?"
    r"(?P<major>[0-9]+)\."
    r"(?P<minor>[0-9]+)"
    r"(?:\.(?P<patch>[0-9]+))?"
    r"(?![0-9])"
)
GO_MOD_RE = re.compile(r"^\s*go\s+(?P<version>\S+)(?:\s+//.*)?\s*$")
GO_OUTPUT_RE = re.compile(r"\bgo(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)\b")
AWS_OUTPUT_RE = re.compile(
    r"\baws-cli/(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)?)\b"
)
_HOME_BIN: Path = Path.home() / "bin"


def _get_python_user_scripts() -> Path:
    """Return the Python user-scheme Scripts directory for the running interpreter.

    Windows: %APPDATA%\\Python\\Python3XX\\Scripts  (nt_user scheme)
    POSIX:   ~/.local/bin                           (posix_user scheme)
    Falls back to a derived path when sysconfig returns None.
    """
    scheme = "nt_user" if sys.platform == "win32" else "posix_user"
    raw = sysconfig.get_path("scripts", scheme)
    if raw:
        return Path(raw)
    # sysconfig fallback (edge case: non-standard Python builds)
    if sys.platform == "win32":
        ver = f"Python{sys.version_info.major}{sys.version_info.minor}"
        return Path.home() / "AppData" / "Roaming" / "Python" / ver / "Scripts"
    return Path.home() / ".local" / "bin"


_PYTHON_USER_SCRIPTS: Path = _get_python_user_scripts()


class VerificationError(Exception):
    """Expected validation or environment verification failure."""


class ValidationError(VerificationError):
    """Repository metadata or verifier input is invalid."""


class UnsupportedPlatformError(VerificationError):
    """The host platform or architecture is unsupported."""


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(
        cls,
        value: str,
        *,
        source: str,
        require_patch: bool = True
    ) -> "Version":
        candidate = value.strip()

        if not candidate:
            raise ValidationError(f"{source}: version is empty")

        match = CONCRETE_VERSION_RE.fullmatch(candidate)
        if match:
            return cls(
                major=int(match.group("major")),
                minor=int(match.group("minor")),
                patch=int(match.group("patch")),
            )

        if not require_patch:
            match = VERSION_RE.fullmatch(candidate)
            if match:
                return cls(
                    major=int(match.group("major")),
                    minor=int(match.group("minor")),
                    patch=int(match.group("patch") or 0),
                )

        raise ValidationError(
            f"{source}: expected a concrete numeric version "
            f"{'X.Y.Z' if require_patch else 'X.Y or X.Y.Z'}, got {value!r}"
        )

    @classmethod
    def from_parts(cls, value: str, *, source: str) -> "Version":
        return cls.parse(value, source=source, require_patch=False)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def same_major_minor(self, other: "Version") -> bool:
        return (self.major, self.minor) == (other.major, other.minor)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    executables: tuple[str, ...]
    arguments: tuple[str, ...]
    output_pattern: Optional[re.Pattern[str]] = None
    python_probe: bool = False
    patch_tolerance: int = 0
    extra_search_dirs: tuple[Path, ...] = ()


@dataclass
class ToolResult:
    name: str
    required: str
    status: str
    executable: Optional[str] = None
    detected: Optional[str] = None
    detail: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.status in {"passed", "skipped"}

    def as_dict(self) -> dict[str, object]:
        return {
            "tool": self.name,
            "required": self.required,
            "detected": self.detected,
            "executable": self.executable,
            "status": self.status,
            "detail": self.detail,
        }


TOOL_SPECS: dict[str, ToolSpec] = {
    "terraform": ToolSpec(
        "terraform", ("terraform",), ("version",),
        re.compile(r"\bTerraform\s+v?(?P<version>[0-9]+\.[0-9]+\.[0-9]+)")
    ),
    "terragrunt": ToolSpec(
        "terragrunt", ("terragrunt",), ("--version",)
    ),
    "golang": ToolSpec(
        "golang", ("go",), ("version",), GO_OUTPUT_RE, patch_tolerance=9
    ),
    "python": ToolSpec(
        "python", ("python3", "python"), (), python_probe=True
    ),
    "nodejs": ToolSpec(
        "nodejs", ("node",), ("--version",)
    ),
    "awscli": ToolSpec(
        "awscli", ("aws",), ("--version",), AWS_OUTPUT_RE
    ),
    "docker-cli": ToolSpec(
        "docker-cli", ("docker",), ("--version",)
    ),
    "tflint": ToolSpec("tflint", ("tflint",), ("--version",)),
    "trivy": ToolSpec("trivy", ("trivy",), ("--version",)),
    "checkov": ToolSpec("checkov", ("checkov",), ("--version",)),
    "yamllint": ToolSpec(
        "yamllint", ("yamllint",), ("--version",),
        extra_search_dirs=(_PYTHON_USER_SCRIPTS,),
    ),
    "shellcheck": ToolSpec("shellcheck", ("shellcheck",), ("--version",)),
    "shfmt": ToolSpec("shfmt", ("shfmt",), ("--version",)),
    "markdownlint-cli2": ToolSpec(
        "markdownlint-cli2", ("markdownlint-cli2",), ("--version",)
    ),
    "gitleaks": ToolSpec("gitleaks", ("gitleaks",), ("version",)),
    "actionlint": ToolSpec("actionlint", ("actionlint",), ("-version",)),
    "golangci-lint": ToolSpec(
        "golangci-lint", ("golangci-lint",), ("version",)
    ),
    "task": ToolSpec("task", ("task",), ("--version",)),
    "just": ToolSpec("just", ("just",), ("--version",)),
    "make": ToolSpec("make", ("gmake", "make"), ("--version",)),
    "pre-commit": ToolSpec("pre-commit", ("pre-commit",), ("--version",)),
    "jq": ToolSpec(
        "jq", ("jq",), ("--version",), extra_search_dirs=(_HOME_BIN,)
    ),
    "yq": ToolSpec(
        "yq", ("yq",), ("--version",), extra_search_dirs=(_HOME_BIN,)
    ),
    "terraform-docs": ToolSpec(
        "terraform-docs", ("terraform-docs",), ("--version",)
    ),
}


def parse_args(argv: Optional[Iterable[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify the pinned repository development environment."
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="repository root; defaults to the root derived from this script",
    )
    parser.add_argument(
        "--platform",
        help="platform override: windows, linux, macos, darwin, or posix",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"per-command timeout in seconds; default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON instead of the normal report",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="emit no human-readable output unless verification fails",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def resolve_root(override: Optional[Path]) -> Path:
    if override is not None:
        root = override.expanduser().resolve()
    else:
        script_path = Path(__file__).resolve()
        try:
            root = script_path.parents[2]
        except IndexError as exc:
            raise ValidationError(
                f"cannot derive repository root from {script_path}"
            ) from exc

    if not root.is_dir():
        raise ValidationError(f"repository root is not a directory: {root}")

    return root


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ValidationError(f"required file is missing: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc


def parse_tool_versions(path: Path) -> dict[str, Version]:
    content = read_text(path)
    versions: dict[str, Version] = {}

    for line_number, original in enumerate(content.splitlines(), start=1):
        line = original.split("#", 1)[0].strip()
        if not line:
            continue

        fields = line.split()
        if len(fields) != 2:
            raise ValidationError(
                f"{path}:{line_number}: expected '<tool> <version>', "
                f"got {original!r}"
            )

        name, value = fields
        if not TOOL_NAME_RE.fullmatch(name):
            raise ValidationError(
                f"{path}:{line_number}: invalid tool name {name!r}"
            )

        if name in versions:
            raise ValidationError(
                f"{path}:{line_number}: duplicate tool entry {name!r}"
            )

        versions[name] = Version.parse(
            value,
            source=f"{path}:{line_number} ({name})",
            require_patch=True,
        )

    if not versions:
        raise ValidationError(f"tool versions file contains no active entries: {path}")

    return versions


def validate_mirror(
    canonical: Mapping[str, Version],
    mirror_path: Path,
) -> None:
    mirror = parse_tool_versions(mirror_path)

    canonical_names = set(canonical)
    mirror_names = set(mirror)

    missing = sorted(canonical_names - mirror_names)
    unexpected = sorted(mirror_names - canonical_names)

    if missing or unexpected:
        details: list[str] = []
        if missing:
            details.append(f"missing={', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected={', '.join(unexpected)}")
        raise ValidationError(
            f"tool version mirror differs from canonical inventory: "
            f"{'; '.join(details)}"
        )

    mismatches = [
        f"{name}: canonical={canonical[name]}, mirror={mirror[name]}"
        for name in sorted(canonical_names)
        if canonical[name] != mirror[name]
    ]
    if mismatches:
        raise ValidationError(
            "tool version mirror contains version mismatches: "
            + "; ".join(mismatches)
        )


def parse_go_mod_version(path: Path) -> Version:
    content = read_text(path)
    matches: list[tuple[int, str]] = []


    for line_number, original in enumerate(content.splitlines(), start=1):
            stripped = original.strip()
            if not stripped or stripped.startswith("//"):
                continue

            if stripped == "go" or stripped.startswith("go "):
                match = GO_MOD_RE.fullmatch(original)
                if not match:
                    raise ValidationError(
                        f"{path}:{line_number}: malformed go directive: {original!r}"
                    )
                matches.append((line_number, match.group("version")))

    if not matches:
        raise ValidationError(f"go directive is missing from {path}")

    if len(matches) != 1:
        raise ValidationError(
            f"go directive is ambiguous; found {len(matches)} entries in {path}"
        )

    line_number, value = matches[0]
    return Version.parse(
        value,
        source=f"{path}:{line_number} (go directive)",
        require_patch=False,
    )


def validate_go_contract(
    canonical: Mapping[str, Version],
    go_mod_path: Path,
) -> None:
    required = canonical.get("golang")
    if required is None:
        raise ValidationError("golang entry is missing from tooling/.tool-versions")

    go_mod = parse_go_mod_version(go_mod_path)

    if not required.same_major_minor(go_mod):
        raise ValidationError(
            f"Go version mismatch: tooling pin={required}, go.mod={go_mod}"
        )

    # A patchless go.mod directive is compatible with any patch in the same major/minor release
    if go_mod.patch != 0 and required != go_mod:
        raise ValidationError(
            f"Go patch version mismatch: tooling pin={required}, go.mod={go_mod}"
        )


def normalize_platform(value: str, source: str) -> str:
    aliases = {
        "windows": "windows",
        "win32": "windows",
        "linux": "linux",
        "macos": "macos",
        "darwin": "macos",
        "osx": "macos",
        "posix": "posix",
    }

    normalized = value.strip().lower()
    if normalized not in aliases:
        raise UnsupportedPlatformError(
            f"unsupported platform {value!r} from {source}; "
            "supported values: windows, linux, macos, posix"
        )

    return aliases[normalized]


def detect_platform(explicit: Optional[str]) -> str:
    if explicit:
        return normalize_platform(explicit, "--platform")

    for variable in (
        "CROSS_PLATFORM_PLATFORM",
        "SETUP_PLATFORM",
        "BOOTSTRAP_WRAPPER_OS",
    ):
        value = os.environ.get(variable, "").strip()
        if value:
            return normalize_platform(value, variable)

    detected = host_platform.system()
    aliases = {
        "Windows": "windows",
        "Linux": "linux",
        "Darwin": "macos",
    }
    if detected not in aliases:
        raise UnsupportedPlatformError(
            f"unsupported host operating system {detected!r}"
        )

    return aliases[detected]


def validate_architecture() -> str:
    machine = host_platform.machine().strip().lower()
    aliases = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }

    normalized = aliases.get(machine)
    if normalized is None:
        raise UnsupportedPlatformError(
            f"unsupported architecture {machine!r}; "
            "supported architectures: amd64 and arm64"
        )

    return normalized


def parse_version_from_output(
    output: str,
    *,
    spec: ToolSpec,
    source: str,
) -> Version:
    pattern = spec.output_pattern or VERSION_RE
    match = pattern.search(output)

    if not match:
        raise VerificationError(
            f"{source}: unable to parse a version from output "
            f"{output.strip()!r}"
        )

    raw = match.groupdict().get("version")
    if raw is None:
        raw = ".".join(
            match.group(name) or "0"
            for name in ("major", "minor", "patch")
        )
    return Version.from_parts(raw, source=source)


def run_command(
    executable: str,
    arguments: tuple[str, ...],
    timeout: float,
) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            [executable, *arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise VerificationError(f"executable disappeared: {executable}") from exc
    except subprocess.TimeoutExpired as exc:
        raise VerificationError(
            f"command timed out after {timeout:.1f}s: "
            f"{executable} {' '.join(arguments)}"
        ) from exc
    except OSError as exc:
        raise VerificationError(
            f"cannot execute {executable}: {exc}"
        ) from exc

    output = "\n".join(
        part.strip()
        for part in (completed.stdout, completed.stderr)
        if part and part.strip()
    ).strip()

    return completed.returncode, output


def query_python_version(
    executable: str,
    timeout: float,
) -> Version:
    probe = (
        "import sys; "
        "print('.'.join(str(part) for part in sys.version_info[:3]))"
    )
    return_code, output = run_command(executable, ("-c", probe), timeout)

    if return_code != 0:
        raise VerificationError(
            f"{executable}: Python probe exited with status {return_code}: "
            f"{output!r}"
        )

    return Version.parse(
        output,
        source=f"{executable} Python runtime",
        require_patch=True,
    )


def find_executable(
    candidates: tuple[str, ...],
    extra_dirs: tuple[Path, ...] = (),
) -> Optional[str]:
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    if extra_dirs:
        extra_path = os.pathsep.join(str(d) for d in extra_dirs if d.is_dir())
        if extra_path:
            for candidate in candidates:
                resolved = shutil.which(candidate, path=extra_path)
                if resolved:
                    return resolved
    return None


def verify_tool(
    name: str,
    required: Version,
    timeout: float,
) -> ToolResult:
    spec = TOOL_SPECS.get(name)
    if spec is None:
        return ToolResult(
            name=name,
            required=str(required),
            status="unsupported",
            detail="no verification mapping exists for this tool",
        )

    executable = find_executable(spec.executables, spec.extra_search_dirs)
    if executable is None:
        return ToolResult(
            name=name,
            required=str(required),
            status="missing",
            detail=f"none of these executables was found: {', '.join(spec.executables)}",
        )

    try:
        if spec.python_probe:
            detected = query_python_version(executable, timeout)
        else:
            return_code, output = run_command(
                executable,
                spec.arguments,
                timeout,
            )
            if return_code != 0:
                raise VerificationError(
                    f"command exited with status {return_code}: {output!r}"
                )
            detected = parse_version_from_output(
                output,
                spec=spec,
                source=f"{name} ({executable})",
            )
    except VerificationError as exc:
        return ToolResult(
            name=name,
            required=str(required),
            status="unusable",
            executable=executable,
            detail=str(exc),
        )

    if detected != required:
        if (
            spec.patch_tolerance > 0
            and detected.same_major_minor(required)
            and required.patch <= detected.patch <= required.patch + spec.patch_tolerance
        ):
            return ToolResult(
                name=name,
                required=str(required),
                detected=str(detected),
                executable=executable,
                status="passed",
            )
        return ToolResult(
            name=name,
            required=str(required),
            detected=str(detected),
            executable=executable,
            status="mismatch",
            detail=f"required {required}, detected {detected}",
        )

    return ToolResult(
        name=name,
        required=str(required),
        detected=str(detected),
        executable=executable,
        status="passed",
    )


def format_result(result: ToolResult) -> str:
    executable = f" [{result.executable}]" if result.executable else ""
    detected = result.detected or "-"
    detail = f" - {result.detail}" if result.detail else ""

    return (
        f"{result.name:<20} "
        f"required={result.required:<10} "
        f"detected={detected:<10} "
        f"status={result.status}{executable}{detail}"
    )


def print_human_report(
    *,
    root: Path,
    platform_name: str,
    architecture: str,
    results: list[ToolResult],
) -> None:
    print(f"repository:   {root}")
    print(f"platform:     {platform_name}")
    print(f"architecture: {architecture}")
    print()
    print("tool verification:")

    for result in results:
        print(f"  {format_result(result)}")

    failed = [result for result in results if not result.passed]
    print()
    if failed:
        print(
            f"FAILED: {len(failed)} of {len(results)} required tool checks failed.",
            file=sys.stderr,
        )
    else:
        print(f"PASSED: all {len(results)} required tool checks passed.")


def run(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)

    if args.timeout <= 0:
        raise ValidationError("--timeout must be greater than zero")

    root = resolve_root(args.root)
    platform_name = detect_platform(args.platform)
    architecture = validate_architecture()

    tooling_dir = root / "tooling"
    canonical_path = tooling_dir / ".tool-versions"
    mirror_path = tooling_dir / "cross-platform" / "asdf-tool-versions"
    go_mod_path = root / "go.mod"

    canonical = parse_tool_versions(canonical_path)
    validate_mirror(canonical, mirror_path)
    validate_go_contract(canonical, go_mod_path)

    unknown_tools = sorted(set(canonical) - set(TOOL_SPECS))
    if unknown_tools:
        raise ValidationError(
            "no verification mapping exists for tool(s): "
            + ", ".join(unknown_tools)
        )

    results = [
        verify_tool(name, canonical[name], args.timeout)
        for name in canonical
    ]

    if args.json:
        payload = {
            "repository": str(root),
            "platform": platform_name,
            "architecture": architecture,
            "passed": all(result.passed for result in results),
            "results": [result.as_dict() for result in results],
        }
        print(json.dumps(payload, indent=2, sort_keys=False))
    elif not args.quiet or any(not result.passed for result in results):
        print_human_report(
            root=root,
            platform_name=platform_name,
            architecture=architecture,
            results=results,
        )

    return EXIT_OK if all(result.passed for result in results) else EXIT_ENVIRONMENT


def main(argv: Optional[Iterable[str]] = None) -> int:
    try:
        return run(argv)
    except ValidationError as exc:
        print(f"ERROR: validation failed: {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    except UnsupportedPlatformError as exc:
        print(f"ERROR: unsupported platform: {exc}", file=sys.stderr)
        return EXIT_PLATFORM
    except KeyboardInterrupt:
        print("ERROR: interrupted by user", file=sys.stderr)
        return EXIT_INTERRUPTED
    except Exception as exc:
        print(f"ERROR: unexpected verifier failure: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    raise SystemExit(main())
