#!/usr/bin/env python3
"""Cross-platform Go/toolchain setup source of truth.

The POSIX and PowerShell wrappers are intentionally thin.  They may provide a
normalized platform through ``--platform`` or one of the environment variables
documented in :func:`detect_platform`; direct invocation falls back to
``platform.system()``.

The Go version policy is deterministic:

* ``tooling/.tool-versions`` must contain a concrete ``golang`` pin with a
  patch component.  That is the selected installer version.
* ``go.mod`` must contain ``go X.Y`` or ``go X.Y.Z``.
* Major/minor components must agree.  If ``go.mod`` includes a patch component,
  it must agree exactly; a patchless ``go.mod`` directive is compatible with
  any concrete patch pin for the same major/minor release.

The current mirror is a full mirror of ``tooling/.tool-versions``.  Both files
are parsed before any external command is started.
"""

from __future__ import annotations

import argparse
import logging
import os
import platform as host_platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional


EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_INSTALLER = 3
EXIT_PLATFORM = 4
EXIT_POST_INSTALL = 5
EXIT_INTERRUPTED = 130
EXIT_UNEXPECTED = 99

DEFAULT_COMMAND_TIMEOUT = 60.0
INSTALLER_TIMEOUT = 1800.0

LOGGER = logging.getLogger("cross-platform-setup")

_VERSION_RE = re.compile(
    r"^(?:v)?(?P<major>0|[1-9][0-9]*)\."
    r"(?P<minor>0|[1-9][0-9]*)"
    r"(?:\.(?P<patch>0|[1-9][0-9]*))?"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_GO_MOD_RE = re.compile(r"^\s*go\s+(?P<version>\S+)(?:\s+//.*)?\s*$")
_FLOATING_VERSIONS = {
    "latest",
    "stable",
    "current",
    "head",
    "master",
    "main",
    "*",
}


class SetupError(Exception):
    """Base class for expected setup failures."""


class ValidationError(SetupError):
    """Repository or input validation failed."""


class UnsupportedPlatformError(SetupError):
    """The requested host platform is not supported."""


class InstallerError(SetupError):
    """The Go installer command failed."""


class PostInstallError(SetupError):
    """Post-installation verification failed."""


@dataclass(frozen=True)
class ParsedVersion:
    raw: str
    parts: tuple[int, ...]

    @property
    def has_patch(self) -> bool:
        return len(self.parts) == 3

    @property
    def comparable(self) -> tuple[int, int, int]:
        return (*self.parts, 0)[:3]

    def __str__(self) -> str:
        return ".".join(str(part) for part in self.parts)


@dataclass(frozen=True)
class InstalledGo:
    executable: Optional[str]
    version: Optional[ParsedVersion]
    output: str = ""
    error: Optional[str] = None


def configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )


def find_repository_root(
    script_path: Optional[Path] = None,
    override: Optional[Path] = None,
) -> Path:
    """Resolve the repository from the script location, never from cwd."""
    if override is not None:
        root = override.expanduser().resolve()
        if not root.is_dir():
            raise ValidationError(f"repository root is not a directory: {root}")
        return root

    script = (script_path or Path(__file__)).resolve()
    try:
        root = script.parents[2]
    except IndexError as exc:
        raise ValidationError(
            f"cannot derive repository root from setup script: {script}"
        ) from exc
    if not root.is_dir():
        raise ValidationError(f"derived repository root is not a directory: {root}")
    return root


def parse_version(
    value: str,
    *,
    source: str = "version",
    require_patch: bool = False,
) -> ParsedVersion:
    """Parse a pinned numeric X.Y or X.Y.Z version."""
    candidate = value.strip()
    if not candidate or candidate.lower() in _FLOATING_VERSIONS:
        raise ValidationError(
            f"{source}: version must be a concrete numeric pin, got {value!r}"
        )
    if any(char in candidate for char in "<>~=*|,^/ "):
        raise ValidationError(
            f"{source}: version ranges and floating values are unsupported: "
            f"{value!r}"
        )
    match = _VERSION_RE.fullmatch(candidate)
    if not match:
        raise ValidationError(f"{source}: malformed version: {value!r}")
    parts = tuple(
        int(match.group(name))
        for name in ("major", "minor", "patch")
        if match.group(name) is not None
    )
    if require_patch and len(parts) != 3:
        raise ValidationError(
            f"{source}: a concrete X.Y.Z version is required, got {value!r}"
        )
    return ParsedVersion(raw=candidate, parts=parts)


def parse_tool_versions(path: Path) -> dict[str, ParsedVersion]:
    """Parse an asdf-style file and reject duplicate or ambiguous entries."""
    if not path.is_file():
        raise ValidationError(f"missing tool versions file: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read tool versions file {path}: {exc}") from exc

    tools: dict[str, ParsedVersion] = {}
    for line_number, original in enumerate(content.splitlines(), start=1):
        line = original.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ValidationError(
                f"{path}:{line_number}: expected '<tool> <version>', got {original!r}"
            )
        tool, value = fields
        if tool in tools:
            raise ValidationError(f"{path}:{line_number}: duplicate tool entry {tool!r}")
        tools[tool] = parse_version(
            value,
            source=f"{path}:{line_number} ({tool})",
        )
    if not tools:
        raise ValidationError(f"tool versions file is empty: {path}")
    return tools


def parse_go_mod_version(path: Path) -> ParsedVersion:
    """Read exactly one Go module ``go`` directive."""
    if not path.is_file():
        raise ValidationError(f"missing go.mod: {path}")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read go.mod {path}: {exc}") from exc

    matches: list[tuple[int, str]] = []
    for line_number, original in enumerate(lines, start=1):
        stripped = original.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if stripped == "go" or stripped.startswith("go "):
            match = _GO_MOD_RE.fullmatch(original)
            if not match:
                raise ValidationError(
                    f"{path}:{line_number}: malformed go directive: {original!r}"
                )
            matches.append((line_number, match.group("version")))
    if not matches:
        raise ValidationError(f"go directive is missing from {path}")
    if len(matches) != 1:
        raise ValidationError(f"go directive is ambiguous; found multiple entries in {path}")
    line_number, value = matches[0]
    return parse_version(
        value,
        source=f"{path}:{line_number} (go directive)",
    )


def validate_go_versions(
    tool_versions: Mapping[str, ParsedVersion],
    go_mod_version: ParsedVersion,
) -> ParsedVersion:
    """Validate and select the concrete ``golang`` pin."""
    selected = tool_versions.get("golang")
    if selected is None:
        raise ValidationError("golang entry is missing from tooling/.tool-versions")
    if not selected.has_patch:
        raise ValidationError(
            "tooling/.tool-versions golang entry must be a concrete X.Y.Z pin"
        )
    if selected.parts[:2] != go_mod_version.parts[:2]:
        raise ValidationError(
            "Go version mismatch: tooling/.tool-versions="
            f"{selected} but go.mod={go_mod_version}"
        )
    if go_mod_version.has_patch and selected.comparable != go_mod_version.comparable:
        raise ValidationError(
            "Go patch version mismatch: tooling/.tool-versions="
            f"{selected} but go.mod={go_mod_version}"
        )
    return selected


def compare_versions(left: ParsedVersion | str, right: ParsedVersion | str) -> int:
    """Compare semantic numeric versions, returning -1, 0, or 1."""
    left_version = (
        left if isinstance(left, ParsedVersion) else parse_version(left, source="version")
    )
    right_version = (
        right if isinstance(right, ParsedVersion) else parse_version(right, source="version")
    )
    if left_version.comparable < right_version.comparable:
        return -1
    if left_version.comparable > right_version.comparable:
        return 1
    return 0


def _semantic_equal(left: ParsedVersion, right: ParsedVersion) -> bool:
    return compare_versions(left, right) == 0


def validate_mirror(
    source: Mapping[str, ParsedVersion],
    mirror_path: Path,
) -> dict[str, ParsedVersion]:
    """Validate the full mirror contract used by this repository."""
    mirror = parse_tool_versions(mirror_path)
    if set(mirror) != set(source):
        missing = sorted(set(source) - set(mirror))
        extra = sorted(set(mirror) - set(source))
        details = []
        if missing:
            details.append(f"missing={', '.join(missing)}")
        if extra:
            details.append(f"unexpected={', '.join(extra)}")
        raise ValidationError(
            f"mirror tool inventory differs from tooling/.tool-versions ({'; '.join(details)})"
        )
    for tool in sorted(source):
        if not _semantic_equal(source[tool], mirror[tool]):
            raise ValidationError(
                f"mirror version mismatch for {tool}: source={source[tool]} "
                f"mirror={mirror[tool]}"
            )
    if "golang" not in mirror:
        raise ValidationError("golang entry is missing from mirror file")
    if not mirror["golang"].has_patch:
        raise ValidationError("mirror golang entry must be a concrete X.Y.Z pin")
    return mirror


_PLATFORM_ALIASES = {
    "windows": "windows",
    "win32": "windows",
    "linux": "linux",
    "macos": "macos",
    "darwin": "macos",
    "osx": "macos",
    "posix": "posix",
}
_PLATFORM_ENV_VARS = (
    "CROSS_PLATFORM_PLATFORM",
    "SETUP_PLATFORM",
    "BOOTSTRAP_WRAPPER_OS",
)


def _normalize_platform(value: str, *, source: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _PLATFORM_ALIASES:
        supported = ", ".join(sorted({"windows", "linux", "macos", "posix"}))
        raise UnsupportedPlatformError(
            f"unsupported platform {value!r} from {source}; supported values: {supported}"
        )
    return _PLATFORM_ALIASES[normalized]


def detect_platform(explicit: Optional[str] = None) -> str:
    """Prefer wrapper/CLI context, with a validated direct-invocation fallback."""
    if explicit is not None:
        return _normalize_platform(explicit, source="--platform")
    for variable in _PLATFORM_ENV_VARS:
        value = os.environ.get(variable)
        if value is not None and value.strip():
            return _normalize_platform(value, source=variable)
    raw = host_platform.system()
    aliases = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}
    if raw in aliases:
        return aliases[raw]
    raise UnsupportedPlatformError(
        f"unsupported host operating system {raw!r}; use --platform with a supported value"
    )


def _parse_go_version_output(output: str) -> Optional[ParsedVersion]:
    match = re.search(r"\bgo(?P<version>\d+\.\d+(?:\.\d+)?)\b", output)
    if not match:
        return None
    try:
        return parse_version(match.group("version"), source="go version output")
    except ValidationError:
        return None


def find_installed_go(timeout: float = DEFAULT_COMMAND_TIMEOUT) -> InstalledGo:
    """Locate Go and safely query its version without raising on normal absence."""
    executable = shutil.which("go")
    if not executable:
        return InstalledGo(executable=None, version=None, error="go executable not found on PATH")
    try:
        completed = subprocess.run(
            [executable, "version"],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError:
        return InstalledGo(executable=executable, version=None, error="go executable disappeared")
    except subprocess.TimeoutExpired:
        return InstalledGo(executable=executable, version=None, error="go version timed out")
    except OSError as exc:
        return InstalledGo(executable=executable, version=None, error=str(exc))

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    version = _parse_go_version_output(output)
    if completed.returncode != 0:
        return InstalledGo(
            executable=executable,
            version=version,
            output=output,
            error=f"go version exited with status {completed.returncode}",
        )
    if version is None:
        return InstalledGo(
            executable=executable,
            version=None,
            output=output,
            error="unable to parse go version output",
        )
    return InstalledGo(executable=executable, version=version, output=output)


def _installer_path(root: Path, platform_name: str) -> Path:
    if platform_name == "windows":
        return root / "scripts" / "tools" / "install-tools-windows.go"
    if platform_name in {"linux", "macos", "posix"}:
        return root / "scripts" / "tools" / "install-tools-posix.go"
    raise UnsupportedPlatformError(f"unsupported platform for installer routing: {platform_name}")


def run_installer(
    root: Path,
    platform_name: str,
    go: InstalledGo,
    *,
    dry_run: bool = False,
    timeout: float = INSTALLER_TIMEOUT,
) -> None:
    """Run the repository installer using its established ``go run`` interface."""
    installer = _installer_path(root, platform_name)
    if not installer.is_file():
        raise ValidationError(f"installer file is missing: {installer}")
    if not go.executable:
        if dry_run:
            LOGGER.info(
                "DRY-RUN: would run [go, run, %s], but Go is not currently available",
                installer,
            )
            return
        raise InstallerError(
            "cannot run the Go installer because no Go executable is available; "
            "install Go or make it available on PATH, then rerun setup"
        )

    command = [go.executable, "run", str(installer)]
    if dry_run:
        LOGGER.info("DRY-RUN: would run %s", command)
        return
    LOGGER.info("running installer: %s", installer)
    try:
        completed = subprocess.run(
            command,
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise InstallerError(f"installer command could not be started: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise InstallerError(
            f"installer timed out after {timeout:.0f} seconds: {installer}"
        ) from exc
    except OSError as exc:
        raise InstallerError(f"failed to execute installer {installer}: {exc}") from exc

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if stdout:
        LOGGER.debug("installer stdout:\n%s", stdout)
    if stderr:
        LOGGER.info("installer stderr:\n%s", stderr)
    if completed.returncode != 0:
        detail = stderr or stdout or "no installer output"
        raise InstallerError(
            f"installer failed with exit code {completed.returncode}: {detail}"
        )


def verify_go_installation(required: ParsedVersion) -> InstalledGo:
    result = find_installed_go()
    if result.version is None:
        detail = result.error or "version unavailable"
        raise PostInstallError(f"Go post-install verification failed: {detail}")
    if not _semantic_equal(result.version, required):
        raise PostInstallError(
            f"Go post-install version mismatch: required={required}, "
            f"detected={result.version} ({result.executable})"
        )
    LOGGER.info("verified Go %s at %s", result.version, result.executable)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and set up the pinned cross-platform Go toolchain."
    )
    parser.add_argument(
        "--platform",
        help="normalized platform: windows, linux, macos, darwin, or posix",
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="optional repository root override (default: derived from this script)",
    )
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and print intended actions without changing the system",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="disable interactive behavior (accepted for CI/wrapper compatibility)",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    verbose = "--verbose" in args_list
    configure_logging(verbose)
    try:
        args = build_parser().parse_args(args_list)
        root = find_repository_root(override=args.root)
        tooling = root / "tooling"
        source_path = tooling / ".tool-versions"
        mirror_path = tooling / "cross-platform" / "asdf-tool-versions"
        go_mod_path = root / "go.mod"

        source = parse_tool_versions(source_path)
        go_mod_version = parse_go_mod_version(go_mod_path)
        required = validate_go_versions(source, go_mod_version)
        validate_mirror(source, mirror_path)
        platform_name = detect_platform(args.platform)
        installer = _installer_path(root, platform_name)
        if not installer.is_file():
            raise ValidationError(f"installer file is missing: {installer}")

        LOGGER.info(
            "repository=%s platform=%s selected Go=%s (tool pin=%s, go.mod=%s)",
            root,
            platform_name,
            required,
            required,
            go_mod_version,
        )
        if args.non_interactive or os.environ.get("CI"):
            LOGGER.debug("non-interactive execution enabled")

        installed = find_installed_go()
        if installed.executable and installed.version:
            LOGGER.info("detected Go %s at %s", installed.version, installed.executable)
        elif installed.executable:
            LOGGER.warning(
                "Go executable %s was found but could not be verified: %s",
                installed.executable,
                installed.error or "unknown error",
            )
        else:
            LOGGER.info("required Go %s is not currently available", required)

        if installed.version and _semantic_equal(installed.version, required):
            LOGGER.info("Go %s already satisfies the required pin; no reinstall needed", required)
            return EXIT_OK

        if installed.version:
            LOGGER.info(
                "installed Go %s does not satisfy required Go %s; installer will run",
                installed.version,
                required,
            )
        run_installer(
            root,
            platform_name,
            installed,
            dry_run=args.dry_run,
        )
        if args.dry_run:
            LOGGER.info("dry-run complete; no system changes were made")
            return EXIT_OK
        verify_go_installation(required)
        LOGGER.info("setup completed successfully")
        return EXIT_OK
    except ValidationError as exc:
        LOGGER.error("validation failed: %s", exc)
        return EXIT_VALIDATION
    except UnsupportedPlatformError as exc:
        LOGGER.error("unsupported platform: %s", exc)
        return EXIT_PLATFORM
    except InstallerError as exc:
        LOGGER.error("installer failed: %s", exc)
        return EXIT_INSTALLER
    except PostInstallError as exc:
        LOGGER.error("%s", exc)
        return EXIT_POST_INSTALL
    except KeyboardInterrupt:
        LOGGER.error("interrupted by user")
        return EXIT_INTERRUPTED
    except Exception as exc:  # pragma: no cover - defensive process boundary
        if verbose:
            LOGGER.exception("unexpected error")
        else:
            LOGGER.error("unexpected error: %s", exc)
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    raise SystemExit(main())
