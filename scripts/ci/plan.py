#!/usr/bin/env python3
"""Advisory terragrunt plan for one stack or every stack under live.

Default: known placeholder/credential failures exit 0.
--strict: the terragrunt exit code is preserved (no placeholder bypass).
Without --dir and without TARGET, plans live/ with terragrunt run --all.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Same signals as the previous Task `plan` inline classifier.
_KNOWN = (
    "tbd",
    "placeholder",
    "invalid value",
    "is null",
    "valid credential sources",
    "unable to locate credentials",
    "could not assume role",
    "backend configuration",
    "invalid value for variable",
    "the value cannot be empty",
    "all whitespace",
    "failed to refresh cached credentials",
)


def _target(explicit: str | None) -> Path | None:
    raw = (explicit or os.environ.get("TARGET") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_dir():
        print(f"plan: target is not a directory: {path}", file=sys.stderr)
        raise SystemExit(2)
    return path


def _scope() -> Path:
    path = Path(os.environ.get("LIVE_ROOT") or "live")
    if not path.is_dir():
        print(f"plan: live root is not a directory: {path}", file=sys.stderr)
        raise SystemExit(2)
    return path


def _argv(extra: list[str], single: bool) -> list[str]:
    from_env = [part for part in os.environ.get("TG_ARGS", "").split() if part]
    if single:
        return ["terragrunt", "plan", "-input=false", *from_env, *extra]
    return [
        "terragrunt", "run", "--all", "--queue-exclude-dir", ".",
        "plan", *from_env, "--", "-input=false", *extra,
    ]


def _known(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in _KNOWN)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="fail on every non-zero terragrunt plan; do not pass placeholder errors",
    )
    parser.add_argument("--dir", dest="directory", help="one stack directory; omit to plan every stack under live")
    parser.add_argument("extra", nargs=argparse.REMAINDER, help="extra args after --")
    args = parser.parse_args()
    extra = args.extra[1:] if args.extra and args.extra[0] == "--" else args.extra

    directory = _target(args.directory)
    try:
        completed = subprocess.run(
            _argv(extra, directory is not None),
            cwd=directory if directory is not None else _scope(),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        print(f"plan: failed to launch terragrunt: {exc}", file=sys.stderr)
        return 2

    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)

    combined = f"{completed.stdout}{completed.stderr}"
    tolerated = completed.returncode != 0 and not args.strict and _known(combined)
    if tolerated:
        print(
            "WARN: plan failed for a known placeholder or credential condition; treating as success.",
            file=sys.stderr,
        )

    if completed.returncode == 0:
        result = "ok"
        code = 0
    elif tolerated:
        result = "warning"
        code = 0
    else:
        result = "failed"
        code = completed.returncode or 1

    print(f"PLAN_ADVISORY_RESULT={result}")
    return code


if __name__ == "__main__":
    sys.stdout.flush()
    sys.stderr.flush()
    raise SystemExit(main())
