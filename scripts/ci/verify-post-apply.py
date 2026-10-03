#!/usr/bin/env python3
"""Post-apply configuration check for one inventory stack.

Reads STACK_ID and optional GITHUB_STEP_SUMMARY from the environment.
Runs the repository-wide verify:security-baseline smoke task and reports
inventory live checks as pending. Does not verify deployed AWS posture.
"""

from __future__ import annotations

import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd().resolve()
STACK_ID = os.environ.get("STACK_ID", "")
SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY")
STACK_ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
CHECK_NAME_RE = re.compile(r"[A-Za-z0-9 :/._-]+")
SMOKE_STATUS = {
    0: "PASS",
    1: "FAILED (configuration)",
    2: "OPERATIONAL ERROR (smoke input)",
    3: "OPERATIONAL ERROR (Terragrunt)",
}


def report(result: str, count: int = 0) -> None:
    stack_label = STACK_ID if re.fullmatch(r"[a-z0-9-]+", STACK_ID) else "invalid"
    lines = [
        "### Post-apply configuration check",
        "",
        f"- Stack: `{stack_label}`",
        f"- Repository-wide configuration smoke: **{result}**",
        f"- Inventory live checks pending: **{count}**",
        "- Deployed AWS posture: **not verified**",
        "",
        "Review the selected stack's `post_deploy_checks` in `inventory/deployment-order.yaml`.\n",
    ]
    if SUMMARY:
        with open(SUMMARY, "a", encoding="utf-8") as stream:
            stream.write("\n".join(lines))


def fail(message: str, result: str, count: int = 0) -> None:
    report(result, count)
    print(message, file=sys.stderr)
    raise SystemExit(2)


def load_checks() -> list[str]:
    if not STACK_ID_RE.fullmatch(STACK_ID):
        raise ValueError("invalid stack ID")

    inventory = runpy.run_path(str(ROOT / "scripts/ci/build-plan-matrix.py"))
    entries = inventory["inventory_entries"](ROOT)
    chosen = next((entry for entry in entries if entry["stack_id"] == STACK_ID), None)
    if chosen is None:
        raise ValueError("stack ID is not in the deployment inventory")

    order = inventory["load_yaml"](ROOT / "inventory/deployment-order.yaml")
    matches = [item for item in order["stacks"] if item.get("id") == STACK_ID]
    if len(matches) != 1 or matches[0].get("path") != chosen["path"]:
        raise ValueError("stack metadata does not match the inventory")

    checks = matches[0].get("post_deploy_checks")
    if not isinstance(checks, list) or not checks or not all(
        isinstance(check, str)
        and check.strip()
        and not any(ord(char) < 32 for char in check)
        for check in checks
    ):
        raise ValueError("stack has no valid post-deployment checklist")
    return checks


def run_smoke() -> tuple[int, dict]:
    result = subprocess.run(
        ["task", "--silent", "verify:security-baseline", "JSON=true"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=600,
        check=False,
    )
    data = json.loads(result.stdout)
    code = data["exit_code"]
    if type(code) is not int or code not in (0, 1, 2, 3) or (
        (result.returncode == 0) != (code == 0)
    ):
        raise ValueError("inconsistent smoke result")
    return code, data


def main() -> None:
    try:
        checks = load_checks()
    except Exception:
        fail(
            "verify:post-apply: invalid scope or inventory; no checks ran",
            "OPERATIONAL ERROR (selection or inventory)",
        )

    print(
        f"Selected {STACK_ID}: {len(checks)} live checks remain for operator review.",
        flush=True,
    )
    print("Running repository-wide, configuration-only security smoke task.", flush=True)

    try:
        code, data = run_smoke()
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError, json.JSONDecodeError):
        fail(
            "verify:post-apply: smoke task could not complete reliably",
            "OPERATIONAL ERROR (smoke execution)",
            len(checks),
        )

    for check in data.get("checks", []):
        if check.get("status") == "FAIL":
            name = check.get("name", "")
            safe_name = (
                name
                if isinstance(name, str) and CHECK_NAME_RE.fullmatch(name)
                else "unnamed check"
            )
            print(f"FAIL: {safe_name}")

    status = SMOKE_STATUS[code]
    report(status, len(checks))
    print(f"Configuration smoke: {status}; deployed AWS posture not verified.")
    raise SystemExit(0 if code == 0 else 1 if code == 1 else 2)


if __name__ == "__main__":
    main()
