#!/usr/bin/env python3
"""Validate and bootstrap the Terraform remote-state infrastructure.

This script is the cross-platform source of truth for the first bootstrap
phase. Terraform resources remain owned by the reusable backend-bootstrap
module and the live Terragrunt stack; this CLI only validates context and
orchestrates safe ``terragrunt`` commands.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


EXIT_OK = 0
EXIT_VALIDATION = 2
EXIT_TOOLS = 3
EXIT_AUTHENTICATION = 4
EXIT_TERRAFORM = 5
EXIT_CANCELLED = 6
EXIT_INTERRUPTED = 130
EXIT_UNEXPECTED = 99

DEFAULT_TIMEOUT = 900.0
LOGGER = logging.getLogger("create-backend")

REDACTED_ENV_NAMES = {
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_SECURITY_TOKEN",
    "AWS_PROFILE",
    "TF_VAR_AWS_SECRET_ACCESS_KEY",
    "TF_VAR_AWS_SESSION_TOKEN",
}


class BootstrapError(Exception):
    """Expected, user-actionable bootstrap failure."""


class ValidationError(BootstrapError):
    """Repository, configuration, or argument validation failed."""


class ToolError(BootstrapError):
    """Required executable is missing or unusable."""


class CommandError(BootstrapError):
    """A subprocess failed or timed out."""

    def __init__(self, phase: str, message: str, *, code: int = EXIT_TERRAFORM):
        super().__init__(message)
        self.phase = phase
        self.code = code


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class RepositoryContext:
    root: Path
    stack: Path
    required_files: tuple[Path, ...]
    unresolved: tuple[str, ...]


def configure_logging(*, verbose: bool, quiet: bool) -> None:
    level = logging.DEBUG if verbose else (logging.ERROR if quiet else logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def resolve_root(script_path: Path | None = None, override: Path | None = None) -> Path:
    if override is not None:
        root = override.expanduser().resolve()
    else:
        script = (script_path or Path(__file__)).resolve()
        try:
            root = script.parents[2]
        except IndexError as exc:
            raise ValidationError(f"cannot derive repository root from {script}") from exc
    if not root.is_dir():
        raise ValidationError(f"repository root is not a directory: {root}")
    return root


def required_repository_paths(root: Path) -> tuple[Path, ...]:
    relative = (
        "live/terragrunt.hcl",
        "live/common.hcl",
        "live/catalogs/accounts.hcl",
        "live/catalogs/regions.hcl",
        "live/catalogs/tags.hcl",
        "live/catalogs/module-versions.hcl",
        "live/bootstrap/backend-bootstrap/terragrunt.hcl",
    )
    return tuple(root / item for item in relative)


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise ValidationError(f"required file is missing: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc


def find_unresolved(root: Path, files: Sequence[Path]) -> tuple[str, ...]:
    unresolved: list[str] = []
    pattern = re.compile(r"\bTBD\b", re.IGNORECASE)
    for path in files:
        content = read_text(path)
        for line_number, line in enumerate(content.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue
            if pattern.search(line):
                unresolved.append(f"{path.relative_to(root)}:{line_number}")
    # Missing backend projections are unsafe even when no literal TBD appears.
    common = read_text(root / "live/common.hcl")
    if not re.search(r"(?m)^\s*(?:bootstrap|backend)\s*=", common):
        unresolved.append("live/common.hcl: backend bootstrap metadata is not defined")
    return tuple(unresolved)


def inspect_repository(root: Path) -> RepositoryContext:
    required = required_repository_paths(root)
    missing = [path for path in required if not path.is_file()]
    if missing:
        rendered = ", ".join(str(path.relative_to(root)) for path in missing)
        raise ValidationError(f"repository layout is incomplete; missing: {rendered}")
    stack = root / "live/bootstrap/backend-bootstrap"
    return RepositoryContext(
        root=root,
        stack=stack,
        required_files=required,
        unresolved=find_unresolved(root, required),
    )


def find_tool(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise ToolError(f"required tool '{name}' was not found on PATH")
    return executable


def redact(text: str) -> str:
    result = text
    for name in REDACTED_ENV_NAMES:
        value = os.environ.get(name)
        if value:
            result = result.replace(value, "<redacted>")
    result = re.sub(
        r"(?i)(aws_secret_access_key|aws_session_token|secret_access_key)\s*[=:]\s*\S+",
        r"\1=<redacted>",
        result,
    )
    return result


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    phase: str,
    env: dict[str, str] | None = None,
) -> CommandResult:
    LOGGER.debug("phase=%s command=%s cwd=%s", phase, list(command), cwd)
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
            env=env,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"{phase}: executable could not be started: {command[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(
            phase,
            f"{phase} timed out after {timeout:.0f} seconds",
            code=EXIT_TERRAFORM,
        ) from exc
    except OSError as exc:
        raise CommandError(phase, f"{phase} could not execute: {exc}") from exc

    result = CommandResult(
        tuple(command),
        completed.returncode,
        redact(completed.stdout or ""),
        redact(completed.stderr or ""),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        lowered = detail.lower()
        code = EXIT_AUTHENTICATION if any(
            marker in lowered
            for marker in ("accessdenied", "no credentials", "unable to locate credentials", "invalidclienttokenid")
        ) else EXIT_TERRAFORM
        raise CommandError(
            phase,
            f"{phase} failed with exit code {result.returncode}: "
            f"{detail[:1200] or 'no command output'}",
            code=code,
        )
    if result.stdout.strip():
        LOGGER.debug("%s stdout:\n%s", phase, result.stdout.strip())
    if result.stderr.strip():
        LOGGER.debug("%s stderr:\n%s", phase, result.stderr.strip())
    return result


def validate_tools(*, skip: bool, dry_run: bool) -> tuple[str, str] | None:
    if skip:
        LOGGER.warning("tool checks skipped by request")
        return None
    terraform = find_tool("terraform")
    terragrunt = find_tool("terragrunt")
    if dry_run:
        LOGGER.info("verified tool locations: terraform=%s terragrunt=%s", terraform, terragrunt)
        return terraform, terragrunt
    return terraform, terragrunt


def confirm_apply(*, non_interactive: bool, yes: bool) -> None:
    if non_interactive and not yes:
        raise ValidationError("--apply in non-interactive mode requires --yes")
    if yes:
        return
    try:
        answer = input("Apply the backend bootstrap now? Type 'yes' to continue: ").strip().lower()
    except EOFError as exc:
        raise BootstrapError("user confirmation was unavailable; use --yes in automation") from exc
    if answer != "yes":
        raise BootstrapError("apply cancelled by user")


def command_plan(stack: Path, terragrunt: str, timeout: float) -> None:
    run_command([terragrunt, "init", "--backend=false"], cwd=stack, timeout=timeout, phase="terragrunt init")
    run_command([terragrunt, "validate"], cwd=stack, timeout=timeout, phase="terragrunt validate")
    run_command([terragrunt, "plan"], cwd=stack, timeout=timeout, phase="terragrunt plan")


def command_apply(stack: Path, terragrunt: str, timeout: float) -> None:
    command_plan(stack, terragrunt, timeout)
    run_command([terragrunt, "apply", "-auto-approve"], cwd=stack, timeout=timeout, phase="terragrunt apply")
    LOGGER.info("backend bootstrap apply completed; verify outputs before migration")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely validate, plan, or apply the Terraform remote-state bootstrap stack."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="initialize, validate, and create a Terraform plan (default)")
    mode.add_argument("--apply", action="store_true", help="apply the backend bootstrap after an explicit confirmation")
    parser.add_argument("--dry-run", action="store_true", help="validate inputs and print intended commands without running Terraform")
    parser.add_argument("--non-interactive", action="store_true", help="disable prompts; combine --apply with --yes")
    parser.add_argument("--yes", action="store_true", help="confirm an apply in non-interactive automation")
    parser.add_argument("--allow-unresolved-tbd", action="store_true", help="allow unresolved placeholders for validation/plan only; never permits apply")
    parser.add_argument("--skip-tool-check", action="store_true", help="skip executable discovery (useful for offline dry-runs)")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help=f"timeout per Terraform command in seconds (default: {DEFAULT_TIMEOUT:.0f})")
    parser.add_argument("--working-directory", type=Path, help="repository root override")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    parser.add_argument("--quiet", action="store_true", help="only print errors")
    return parser


def run(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    configure_logging(verbose=args.verbose, quiet=args.quiet)
    if args.timeout <= 0:
        raise ValidationError("--timeout must be greater than zero")
    if args.yes and not args.apply:
        raise ValidationError("--yes is only valid with --apply")
    if args.allow_unresolved_tbd and args.apply:
        raise ValidationError("--allow-unresolved-tbd is never permitted with --apply")

    root = resolve_root(override=args.working_directory)
    context = inspect_repository(root)
    unresolved = context.unresolved
    if unresolved:
        LOGGER.warning("unresolved configuration values detected:\n  %s", "\n  ".join(unresolved))
        if args.apply:
            raise ValidationError(
                "apply refused because account/backend configuration is unresolved; "
                "populate catalog/backend values and rerun"
            )
        if not (args.allow_unresolved_tbd or args.dry_run):
            raise ValidationError(
                "unresolved values prevent a safe plan; use --dry-run or "
                "--allow-unresolved-tbd for validation-only execution"
            )

    tools = validate_tools(skip=args.skip_tool_check, dry_run=args.dry_run)
    terragrunt = tools[1] if tools else "terragrunt"
    if args.dry_run:
        LOGGER.info("repository=%s", root)
        LOGGER.info("stack=%s", context.stack)
        LOGGER.info("DRY-RUN: would run [%s, init, --backend=false]", terragrunt)
        LOGGER.info("DRY-RUN: would run [%s, validate]", terragrunt)
        LOGGER.info("DRY-RUN: would run [%s, plan]", terragrunt)
        return EXIT_OK

    if args.apply:
        confirm_apply(non_interactive=args.non_interactive, yes=args.yes)
        command_apply(context.stack, terragrunt, args.timeout)
    else:
        command_plan(context.stack, terragrunt, args.timeout)
    return EXIT_OK


def main(argv: Iterable[str] | None = None) -> int:
    try:
        return run(argv)
    except KeyboardInterrupt:
        LOGGER.error("interrupted by user")
        return EXIT_INTERRUPTED
    except BootstrapError as exc:
        code = getattr(exc, "code", EXIT_VALIDATION)
        LOGGER.error("%s", exc)
        return code
    except Exception as exc:
        LOGGER.error("unexpected bootstrap failure: %s", exc)
        return EXIT_UNEXPECTED


if __name__ == "__main__":
    raise SystemExit(main())
