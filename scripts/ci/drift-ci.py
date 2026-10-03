"""Read-only drift scan for remote-state stacks. Exit 0 clean, 1 drift, 2 operational error."""

from __future__ import annotations

import os
import re
import runpy
import subprocess
import sys
from pathlib import Path


def report(rows: list[tuple[str, str]]) -> None:
    lines = ["### Read-only infrastructure drift", "", "| Stack | Result |", "| --- | --- |"]
    lines.extend(f"| {stack} | {result} |" for stack, result in rows)
    if not rows:
        lines.append("| None | No remote-state stacks to scan |")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write("\n".join(lines) + "\n")


def category(output: str) -> str:
    value = output.lower()
    if any(word in value for word in ("credential", "accessdenied", "access denied", "assumerole", "assume role")):
        return "authentication/access"
    if any(word in value for word in ("backend", "s3 bucket", "state lock", "dynamodb")):
        return "backend/state access"
    if "provider" in value:
        return "provider"
    return "execution"


def main() -> int:
    root = Path.cwd().resolve()
    rows: list[tuple[str, str]] = []

    try:
        inventory = runpy.run_path(str(root / "scripts/ci/build-plan-matrix.py"))
        entries = inventory["inventory_entries"](root)
        if any(not re.fullmatch(r"[a-z0-9-]+", entry["stack_id"]) for entry in entries):
            raise ValueError("unsafe stack identifier for summary")
        order = inventory["load_yaml"](root / "inventory/deployment-order.yaml")
        bootstrap = order["bootstrap"]
        if bootstrap["state_model"] != "local_then_remote":
            raise ValueError("unsupported bootstrap state model")
        local_ids = {
            step["stack_id"]
            for step in bootstrap["steps"]
            if step.get("kind") == "terragrunt-stack" and step.get("state") == "local"
        }
        if not local_ids or not local_ids <= {entry["stack_id"] for entry in entries}:
            raise ValueError("invalid local-state bootstrap inventory")
        targets = [entry for entry in entries if entry["stack_id"] not in local_ids]
    except Exception:
        rows.append(("inventory", "operational error (metadata or dependency)"))
        report(rows)
        print("drift:ci: inventory/discovery failed; no plans were run", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env.update(TF_IN_AUTOMATION="1", TF_INPUT="0", PYTHONDONTWRITEBYTECODE="1")
    for entry in targets:
        stack, path = entry["stack_id"], root / entry["path"]
        try:
            if not (path / ".terraform.lock.hcl").is_file():
                rows.append((stack, "operational error (missing provider lockfile)"))
                continue
            if 'include "remote_state"' not in (path / "terragrunt.hcl").read_text(encoding="utf-8"):
                rows.append((stack, "operational error (remote state not configured)"))
                continue
        except OSError:
            rows.append((stack, "operational error (cannot read stack metadata)"))
            continue
        for stage, command in (
            ("init", ["terragrunt", "init", "--", "-input=false", "-no-color", "-reconfigure", "-lockfile=readonly", "-lock=false"]),
            ("plan", ["terragrunt", "plan", "--no-auto-init", "--", "-input=false", "-no-color", "-lock=false", "-detailed-exitcode"]),
        ):
            try:
                completed = subprocess.run(
                    command,
                    cwd=path,
                    env=env,
                    text=True,
                    errors="replace",
                    capture_output=True,
                    timeout=300,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                rows.append((stack, f"operational error ({stage} launch/timeout)"))
                break
            if stage == "plan" and completed.returncode == 2:
                rows.append((stack, "drift detected"))
                break
            if completed.returncode != 0:
                reason = category(completed.stdout + completed.stderr)
                rows.append((stack, f"operational error ({stage}: {reason})"))
                break
            if stage == "plan":
                rows.append((stack, "no drift"))

    report(rows)
    for stack, result in rows:
        print(f"{stack}: {result}")
    errors = any(result.startswith("operational error") for _, result in rows)
    drift = any(result == "drift detected" for _, result in rows)
    print(f"Drift scan: {len(targets)} remote-state stacks, drift={drift}, errors={errors}")
    return 2 if errors else 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
