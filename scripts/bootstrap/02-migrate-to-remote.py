#!/usr/bin/env python3
"""Safely migrate live Terragrunt stacks from local to remote state.

The reusable Terraform modules and Terragrunt configuration remain the source
of truth for infrastructure. This script discovers stacks, backs up local
state, validates the remote backend, and orchestrates ``terragrunt init
--migrate-state`` without deleting local recovery artifacts.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_TOOLS = 3
EXIT_AUTH = 4
EXIT_MIGRATION = 5
EXIT_LOCKED = 6
EXIT_INTERRUPTED = 130
EXIT_UNEXPECTED = 99

DEFAULT_TIMEOUT = 900.0
LOGGER = logging.getLogger("migrate-to-remote")
PLACEHOLDER_RE = re.compile(
    r"\b(?:TBD|TODO|CHANGE-ME)\b|<\s*(?:account-id|role-arn|region|bucket|key)\s*>",
    re.IGNORECASE,
)
SENSITIVE_ENV = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
)


class MigrationError(Exception):
    """Expected, actionable migration failure."""


class ValidationError(MigrationError):
    """Repository or configuration validation failure."""


class ToolError(MigrationError):
    """Required executable is unavailable."""


class CommandError(MigrationError):
    """External command failure."""

    def __init__(self, phase: str, message: str, code: int = EXIT_MIGRATION):
        super().__init__(message)
        self.phase = phase
        self.code = code


@dataclass(frozen=True)
class Stack:
    path: Path
    relative: str
    uses_remote_include: bool
    has_local_state: bool
    already_remote: bool


@dataclass(frozen=True)
class StackResult:
    stack: str
    status: str
    backup: str | None = None
    detail: str | None = None


class ProcessLock:
    """Cross-platform exclusive lock using atomic file creation."""

    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    def __enter__(self) -> "ProcessLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = f"pid={os.getpid()}\nutc={datetime.now(timezone.utc).isoformat()}\n"
        try:
            with self.path.open("x", encoding="utf-8") as handle:
                handle.write(payload)
            self.acquired = True
        except FileExistsError as exc:
            stale = "unknown"
            try:
                text = self.path.read_text(encoding="utf-8")
                match = re.search(r"pid=(\d+)", text)
                if match:
                    pid = int(match.group(1))
                    try:
                        os.kill(pid, 0)
                        stale = "active"
                    except OSError:
                        stale = "stale"
            except OSError:
                pass
            raise MigrationError(
                f"migration lock exists at {self.path} ({stale}); "
                "verify no migration is running, then remove the stale lock manually if needed"
            ) from exc
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.acquired:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass


def configure_logging(verbose: bool, quiet: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else (logging.ERROR if quiet else logging.INFO),
        format="%(levelname)s: %(message)s",
    )


def resolve_root(override: Path | None = None) -> Path:
    root = (
        override.expanduser().resolve()
        if override is not None
        else Path(__file__).resolve().parents[2]
    )
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


def redact(text: str) -> str:
    result = text
    for name in SENSITIVE_ENV:
        value = os.environ.get(name)
        if value:
            result = result.replace(value, "<redacted>")
    return re.sub(
        r"(?i)(secret_access_key|session_token)\s*[=:]\s*\S+",
        r"\1=<redacted>",
        result,
    )


def find_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise ToolError(f"required tool '{name}' is not available on PATH")
    return executable


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    phase: str,
    code: int = EXIT_MIGRATION,
) -> tuple[str, str]:
    LOGGER.debug("phase=%s cwd=%s command=%s", phase, cwd, list(command))
    try:
        completed = subprocess.run(
            list(command),
            cwd=str(cwd),
            check=False,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"{phase}: executable not found: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(phase, f"{phase} timed out after {timeout:.0f} seconds", code) from exc
    except OSError as exc:
        raise CommandError(phase, f"{phase} could not execute: {exc}", code) from exc

    stdout = redact(completed.stdout or "")
    stderr = redact(completed.stderr or "")
    if completed.returncode != 0:
        detail = (stderr or stdout).strip()
        lowered = detail.lower()
        classified = EXIT_AUTH if any(
            marker in lowered
            for marker in ("accessdenied", "unable to locate credentials", "no credentials", "invalidclienttokenid")
        ) else code
        raise CommandError(
            phase,
            f"{phase} failed with exit code {completed.returncode}: {detail[:1200] or 'no output'}",
            classified,
        )
    return stdout, stderr


def detect_placeholders(root: Path) -> tuple[str, ...]:
    findings: list[str] = []
    for path in (
        root / "live/common.hcl",
        root / "live/_envcommon/remote-state.hcl",
        root / "live/catalogs/accounts.hcl",
        root / "live/catalogs/regions.hcl",
        root / "live/catalogs/tags.hcl",
        root / "live/catalogs/module-versions.hcl",
    ):
        if not path.is_file():
            continue
        for number, line in enumerate(read_text(path).splitlines(), start=1):
            if not line.lstrip().startswith("#") and PLACEHOLDER_RE.search(line):
                findings.append(f"{path.relative_to(root)}:{number}")
    return tuple(findings)


def has_remote_include(path: Path) -> bool:
    return "_envcommon/remote-state.hcl" in read_text(path).replace("\\", "/")


def local_state_files(path: Path) -> list[Path]:
    files = sorted(path.glob("*.tfstate*"))
    for metadata in (
        path / ".terraform" / "terraform.tfstate",
        path / ".terraform" / "environment",
    ):
        if metadata.is_file():
            files.append(metadata)
    return sorted(set(file for file in files if file.is_file()))


def backup_files(path: Path) -> list[Path]:
    files = local_state_files(path)
    lockfile = path / ".terraform.lock.hcl"
    if lockfile.is_file() and files:
        files.append(lockfile)
    return sorted(set(files))


def already_remote(path: Path) -> bool:
    metadata = path / ".terraform" / "terraform.tfstate"
    if not metadata.is_file():
        return False
    try:
        data = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return data.get("backend", {}).get("type") == "s3"


def discover_stacks(root: Path) -> list[Stack]:
    live = root / "live"
    if not live.is_dir():
        raise ValidationError(f"live directory is missing: {live}")
    stacks: list[Stack] = []
    for config in sorted(live.rglob("terragrunt.hcl")):
        if config.parent == live or config.parent == live / "bootstrap" / "backend-bootstrap":
            continue
        if config.name != "terragrunt.hcl":
            continue
        remote = has_remote_include(config)
        files = local_state_files(config.parent)
        stacks.append(
            Stack(
                path=config.parent,
                relative=config.parent.relative_to(root).as_posix(),
                uses_remote_include=remote,
                has_local_state=bool(files),
                already_remote=already_remote(config.parent),
            )
        )
    return stacks


def select_stacks(stacks: Sequence[Stack], requested: Sequence[str], include: str | None, exclude: str | None, root: Path) -> list[Stack]:
    selected = list(stacks)
    if requested:
        wanted = set()
        for value in requested:
            candidate = Path(value)
            resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
            wanted.add(resolved)
        selected = [stack for stack in selected if stack.path.resolve() in wanted]
    if include:
        selected = [stack for stack in selected if fnmatch.fnmatch(stack.relative, include)]
    if exclude:
        selected = [stack for stack in selected if not fnmatch.fnmatch(stack.relative, exclude)]
    return sorted(selected, key=lambda stack: stack.relative)


def order_stacks(stacks: Sequence[Stack]) -> list[Stack]:
    """Place dependency targets before consumers when config_path is explicit."""
    by_path = {stack.path.resolve(): stack for stack in stacks}
    edges: dict[Path, set[Path]] = {path: set() for path in by_path}
    for stack in stacks:
        try:
            content = read_text(stack.path / "terragrunt.hcl")
        except ValidationError:
            continue
        for raw in re.findall(r'config_path\s*=\s*"([^"]+)"', content):
            target = (stack.path / raw).resolve()
            if target in by_path and target != stack.path.resolve():
                edges[stack.path.resolve()].add(target)

    ordered: list[Stack] = []
    visiting: set[Path] = set()
    visited: set[Path] = set()

    def visit(path: Path) -> None:
        if path in visited:
            return
        if path in visiting:
            raise ValidationError(f"circular Terragrunt dependency detected at {path}")
        visiting.add(path)
        for dependency in sorted(edges[path], key=str):
            visit(dependency)
        visiting.remove(path)
        visited.add(path)
        ordered.append(by_path[path])

    for path in sorted(by_path, key=str):
        visit(path)
    return ordered


def backup_stack(stack: Stack, destination: Path, root: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(destination, 0o700)
    except OSError:
        pass
    target = destination / timestamp / stack.relative
    target.mkdir(parents=True, exist_ok=False)
    try:
        os.chmod(target.parent, 0o700)
        os.chmod(target, 0o700)
    except OSError:
        pass
    source_files = backup_files(stack.path)
    if not local_state_files(stack.path):
        raise ValidationError(f"{stack.relative}: local state disappeared before backup")
    for source in source_files:
        relative = source.relative_to(stack.path)
        output = target / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, output)
        try:
            os.chmod(output, 0o600)
        except OSError:
            pass
    copied = [path for path in target.rglob("*") if path.is_file()]
    if len(copied) != len(source_files):
        raise ValidationError(f"{stack.relative}: backup verification failed")
    LOGGER.info("%s backup=%s", stack.relative, target)
    return target


def parse_backend_value(common: str, key: str) -> str | None:
    match = re.search(rf"(?m)^\s*{re.escape(key)}\s*=\s*\"([^\"]+)\"", common)
    return match.group(1) if match else None


def validate_backend_metadata(root: Path) -> dict[str, str]:
    common = read_text(root / "live/common.hcl")
    values = {
        key: parse_backend_value(common, key)
        for key in ("bucket", "region", "dynamodb_table", "kms_key_id")
    }
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValidationError(
            "remote backend metadata is incomplete in live/common.hcl; "
            f"missing concrete values: {', '.join(missing)}"
        )
    unresolved = [key for key, value in values.items() if PLACEHOLDER_RE.search(value or "")]
    if unresolved:
        raise ValidationError(
            "remote backend metadata contains unresolved placeholders: "
            + ", ".join(unresolved)
        )
    return {key: value for key, value in values.items() if value is not None}


def validate_identity(root: Path, region: str, timeout: float) -> None:
    aws = find_tool("aws")
    stdout, _ = run_command(
        [aws, "sts", "get-caller-identity", "--output", "json"],
        cwd=root,
        timeout=timeout,
        phase="AWS identity validation",
        code=EXIT_AUTH,
    )
    try:
        identity = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ValidationError("AWS identity command returned invalid JSON") from exc
    account_id = str(identity.get("Account", ""))
    if not re.fullmatch(r"\d{12}", account_id):
        raise ValidationError("AWS identity did not return a valid 12-digit account ID")
    configured_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    if configured_region and configured_region != region:
        raise ValidationError(
            f"AWS region mismatch: environment={configured_region}, backend={region}"
        )
    LOGGER.info("validated AWS identity account=%s region=%s", account_id, region)


def verify_backend(root: Path, backend: dict[str, str], timeout: float) -> None:
    aws = find_tool("aws")
    bucket = backend["bucket"]
    region = backend["region"]
    run_command([aws, "s3api", "head-bucket", "--bucket", bucket], cwd=root, timeout=timeout, phase="backend bucket existence", code=EXIT_AUTH)
    location, _ = run_command([aws, "s3api", "get-bucket-location", "--bucket", bucket, "--output", "json"], cwd=root, timeout=timeout, phase="backend bucket region", code=EXIT_AUTH)
    try:
        location_data = json.loads(location)
        actual_location = location_data.get("LocationConstraint") or "us-east-1"
    except json.JSONDecodeError as exc:
        raise ValidationError("backend bucket location command returned invalid JSON") from exc
    if actual_location != region:
        raise ValidationError(f"backend bucket region does not match configured region {region}")
    versioning, _ = run_command([aws, "s3api", "get-bucket-versioning", "--bucket", bucket], cwd=root, timeout=timeout, phase="backend bucket versioning", code=EXIT_AUTH)
    if '"Status": "Enabled"' not in versioning and '"Status":"Enabled"' not in versioning:
        raise ValidationError("backend bucket versioning is not enabled")
    run_command([aws, "s3api", "get-bucket-encryption", "--bucket", bucket], cwd=root, timeout=timeout, phase="backend bucket encryption", code=EXIT_AUTH)
    run_command([aws, "s3api", "get-public-access-block", "--bucket", bucket], cwd=root, timeout=timeout, phase="backend public-access block", code=EXIT_AUTH)
    run_command([aws, "dynamodb", "describe-table", "--table-name", backend["dynamodb_table"], "--output", "json"], cwd=root, timeout=timeout, phase="backend lock table", code=EXIT_AUTH)


def confirm_migration(non_interactive: bool, yes: bool) -> None:
    if non_interactive and not yes:
        raise ValidationError("--migrate in non-interactive mode requires --yes")
    if yes:
        return
    answer = input("Migrate selected local states to the remote backend? Type 'yes' to continue: ").strip().lower()
    if answer != "yes":
        raise MigrationError("migration cancelled by user")


def migrate_stack(stack: Stack, terragrunt: str, backup_root: Path, root: Path, timeout: float, dry_run: bool) -> StackResult:
    if not stack.uses_remote_include:
        return StackResult(stack.relative, "NOT_APPLICABLE", detail="no remote-state include")
    if stack.already_remote:
        return StackResult(stack.relative, "ALREADY_REMOTE", detail="Terraform backend metadata reports s3")
    if not stack.has_local_state:
        return StackResult(stack.relative, "NO_LOCAL_STATE", detail="no local Terraform state files found")
    if dry_run:
        return StackResult(stack.relative, "READY_TO_MIGRATE", detail="dry-run; no backup or migration mutation performed")
    try:
        backup = backup_stack(stack, backup_root, root)
    except (OSError, ValidationError, shutil.Error) as exc:
        return StackResult(stack.relative, "BACKUP_FAILED", detail=str(exc))
    run_command(
        [terragrunt, "init", "-migrate-state"],
        cwd=stack.path,
        timeout=timeout,
        phase=f"{stack.relative} remote-state migration",
    )
    run_command(
        [terragrunt, "state", "pull"],
        cwd=stack.path,
        timeout=timeout,
        phase=f"{stack.relative} remote-state verification",
    )
    metadata = stack.path / ".terraform" / "terraform.tfstate"
    try:
        backend = json.loads(metadata.read_text(encoding="utf-8")).get("backend", {})
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return StackResult(stack.relative, "VERIFICATION_FAILED", str(backup), f"backend metadata could not be read: {exc}")
    if backend.get("type") != "s3" or not backend.get("config", {}).get("key"):
        return StackResult(stack.relative, "VERIFICATION_FAILED", str(backup), "Terraform backend metadata does not show a concrete S3 state key")
    return StackResult(stack.relative, "MIGRATED", str(backup))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover, back up, and safely migrate Terragrunt local state to the configured S3/DynamoDB backend."
    )
    parser.add_argument("--list-stacks", action="store_true", help="list discovered non-bootstrap Terragrunt stacks and state classification")
    parser.add_argument("--stack", action="append", default=[], help="migrate/select one stack path; may be repeated")
    parser.add_argument("--include", help="glob filter against repository-relative stack paths")
    parser.add_argument("--exclude", help="glob filter against repository-relative stack paths")
    parser.add_argument("--plan", action="store_true", help="validate and report migration candidates without mutation")
    parser.add_argument("--dry-run", action="store_true", help="back up candidates and report commands without running migration")
    parser.add_argument("--migrate", action="store_true", help="perform state migration (requires confirmation)")
    parser.add_argument("--non-interactive", action="store_true", help="disable interactive confirmation")
    parser.add_argument("--yes", action="store_true", help="approve migration in non-interactive automation")
    parser.add_argument("--backup-directory", type=Path, help="backup root (default: <repo>/.bootstrap-backups)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"per-command timeout in seconds (default: {DEFAULT_TIMEOUT:.0f})")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    parser.add_argument("--quiet", action="store_true", help="only print errors")
    parser.add_argument("--keep-going", action="store_true", help="continue after a stack failure")
    parser.add_argument("--fail-fast", action="store_true", help="stop after the first stack failure (default)")
    parser.add_argument("--allow-unresolved-tbd", action="store_true", help="allow placeholders only for non-mutating discovery/dry-run")
    parser.add_argument("--skip-tool-check", action="store_true", help="skip Terraform/Terragrunt/AWS CLI discovery for offline modes")
    parser.add_argument("--working-directory", type=Path, help="repository root override")
    return parser


def run(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    configure_logging(args.verbose, args.quiet)
    if args.timeout <= 0:
        raise ValidationError("--timeout must be greater than zero")
    if args.keep_going and args.fail_fast:
        raise ValidationError("--keep-going and --fail-fast are mutually exclusive")
    if args.yes and not args.migrate:
        raise ValidationError("--yes requires --migrate")
    if args.allow_unresolved_tbd and args.migrate:
        raise ValidationError("--allow-unresolved-tbd cannot be used with --migrate")
    if args.dry_run and args.migrate:
        raise ValidationError("--dry-run and --migrate are mutually exclusive")

    root = resolve_root(args.working_directory)
    stacks = order_stacks(select_stacks(discover_stacks(root), args.stack, args.include, args.exclude, root))
    if not stacks:
        raise ValidationError("no Terragrunt stacks matched the requested selection")
    if args.list_stacks:
        for stack in stacks:
            status = "ALREADY_REMOTE" if stack.already_remote else ("READY_TO_MIGRATE" if stack.has_local_state else "NO_LOCAL_STATE")
            print(f"{status:18} {stack.relative}")
        return EXIT_OK

    placeholders = detect_placeholders(root)
    if placeholders:
        LOGGER.warning("unresolved placeholders detected:\n  %s", "\n  ".join(placeholders))
        if args.migrate or not (args.allow_unresolved_tbd or args.dry_run or args.plan):
            raise ValidationError("unresolved placeholders block migration; populate concrete account/backend values first")

    if not args.migrate and (args.plan or args.dry_run):
        backup_root = (args.backup_directory or root / ".bootstrap-backups").expanduser().resolve()
        for stack in stacks:
            result = migrate_stack(stack, "terragrunt", backup_root, root, args.timeout, dry_run=True)
            print(f"{result.status:18} {result.stack}" + (f" - {result.detail}" if result.detail else ""))
        return EXIT_OK

    if not args.migrate:
        for stack in stacks:
            status = "ALREADY_REMOTE" if stack.already_remote else ("READY_TO_MIGRATE" if stack.has_local_state else "NO_LOCAL_STATE")
            print(f"{status:18} {stack.relative}")
        return EXIT_OK

    if not args.skip_tool_check:
        terragrunt = find_tool("terragrunt")
    else:
        terragrunt = "terragrunt"
    backend = validate_backend_metadata(root)
    validate_identity(root, backend["region"], args.timeout)
    verify_backend(root, backend, args.timeout)
    confirm_migration(args.non_interactive, args.yes)
    backup_root = (args.backup_directory or root / ".bootstrap-backups").expanduser().resolve()
    results: list[StackResult] = []
    lock = ProcessLock(root / ".bootstrap-migration.lock")
    with lock:
        for stack in stacks:
            try:
                results.append(migrate_stack(stack, terragrunt, backup_root, root, args.timeout, dry_run=False))
            except MigrationError as exc:
                result = StackResult(stack.relative, "MIGRATION_FAILED", detail=str(exc))
                results.append(result)
                LOGGER.error("%s: %s", stack.relative, exc)
                if not args.keep_going:
                    break
    for result in results:
        print(f"{result.status:18} {result.stack}" + (f" - {result.detail}" if result.detail else ""))
    failures = [result for result in results if result.status in {"MIGRATION_FAILED", "BACKUP_FAILED", "VERIFICATION_FAILED"}]
    return EXIT_MIGRATION if failures else EXIT_OK


def main(argv: Iterable[str] | None = None) -> int:
    try:
        return run(argv)
    except KeyboardInterrupt:
        LOGGER.error("interrupted by user; retain backups and inspect backend metadata before rerunning")
        return EXIT_INTERRUPTED
    except ToolError as exc:
        LOGGER.error("%s", exc)
        return EXIT_TOOLS
    except CommandError as exc:
        LOGGER.error("%s", exc)
        return exc.code
    except MigrationError as exc:
        LOGGER.error("%s", exc)
        return EXIT_VALIDATION
    except Exception as exc:
        LOGGER.error("unexpected migration failure: %s", exc)
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    raise SystemExit(main())
