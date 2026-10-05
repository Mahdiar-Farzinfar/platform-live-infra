#!/usr/bin/env python3
"""Verify the repository's configured security baseline using local renders.

Exit codes: 0 = all evaluated configuration checks pass; 1 = configuration
failure; 2 = invalid CLI/repository input; 3 = Terragrunt unavailable or unable
to run. A zero exit code never establishes deployed AWS security posture.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable


EXIT_OK = 0
EXIT_CONFIG = 1
EXIT_TOOL = 3
EXIT_INTERRUPTED = 130

STACKS = {
    "sandbox GuardDuty": "live/workloads/sandbox-account/us-east-1/security-baseline/terragrunt.hcl",
    "Security GuardDuty": "live/foundation/security/us-east-1/guardduty/terragrunt.hcl",
    "Security CloudTrail": "live/foundation/security/us-east-1/cloudtrail/terragrunt.hcl",
    "Log Archive bucket": "live/foundation/log-archive/us-east-1/log-archive-bucket/terragrunt.hcl",
    "Log Archive KMS": "live/foundation/log-archive/us-east-1/kms/terragrunt.hcl",
}
POLICIES = (
    "policies/scp/deny-create-iam-user.json",
    "policies/scp/deny-disable-cloudtrail.json",
    "policies/scp/restrict-regions.json",
)
FEATURES = frozenset(
    {
        "S3_DATA_EVENTS",
        "EKS_AUDIT_LOGS",
        "EBS_MALWARE_PROTECTION",
        "RDS_LOGIN_EVENTS",
        "LAMBDA_NETWORK_LOGS",
        "RUNTIME_MONITORING",
    }
)
RUNTIME_AGENTS = frozenset(
    {"EC2_AGENT_MANAGEMENT", "ECS_FARGATE_AGENT_MANAGEMENT", "EKS_ADDON_MANAGEMENT"}
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def check(name: str, condition: bool, expectation: str) -> Check:
    return Check(name, "PASS" if condition else "FAIL", expectation)


def inputs_of(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("inputs")
    return value if isinstance(value, dict) else {}


def guardduty_checks(config: dict[str, Any], *, sandbox: bool) -> list[Check]:
    inputs = inputs_of(config)
    scope = "sandbox" if sandbox else "Security"
    features = inputs.get("detector_features")
    feature_map = features if isinstance(features, dict) else {}
    feature_names = set(feature_map)
    enabled_features = feature_names == FEATURES and all(
        isinstance(value, dict) and value.get("enabled") is True
        for value in feature_map.values()
    )
    runtime = feature_map.get("RUNTIME_MONITORING", {})
    agents = runtime.get("additional_configuration") if isinstance(runtime, dict) else None
    admin = inputs.get("organization_admin")
    admin = admin if isinstance(admin, dict) else {}

    results = [
        check(f"{scope} detector", inputs.get("enabled") is True,
              "GuardDuty enabled by the account/Region configuration"),
        check(f"{scope} finding cadence",
              inputs.get("finding_publishing_frequency") == "FIFTEEN_MINUTES",
              "finding publishing frequency is FIFTEEN_MINUTES"),
        check(f"{scope} protection features", enabled_features,
              "all six configured GuardDuty protection features enabled"),
        check(f"{scope} runtime agents",
              isinstance(agents, dict) and set(agents) == RUNTIME_AGENTS
              and all(value is True for value in agents.values()),
              "EC2, ECS/Fargate, and EKS runtime agent management enabled"),
        check(f"{scope} organization ownership",
              admin.get("delegate_admin") is False
              and admin.get("manage_org_configuration") is (not sandbox)
              and admin.get("auto_enable") == ("NEW" if sandbox else "ALL"),
              "delegated registration disabled; org settings match stack ownership"),
    ]
    if sandbox:
        results.append(check("sandbox findings export",
                             inputs.get("publishing_destination", object()) is None,
                             "no unapproved findings destination configured"))
        results.append(check("sandbox organization features",
                             inputs.get("organization_features") == {},
                             "organization features owned by the Security stack"))
    else:
        results.append(check("Security organization features",
                             inputs.get("organization_features") == dict.fromkeys(FEATURES, "ALL"),
                             "all six organization protection features set to ALL"))
    return results


def archive_checks(config: dict[str, Any]) -> list[Check]:
    inputs = inputs_of(config)
    principals = inputs.get("log_delivery_service_principals")
    return [
        check("archive immutability",
              inputs.get("object_lock_enabled") is True
              and inputs.get("object_lock_mode") == "COMPLIANCE"
              and inputs.get("object_lock_retention_days") == 2555,
              "Object Lock COMPLIANCE for 2555 days"),
        check("archive retention and deletion",
              inputs.get("force_destroy") is False
              and inputs.get("expiration_days", object()) is None
              and inputs.get("noncurrent_version_expiration_days") == 2555,
              "no forced deletion or current expiration; noncurrent retention 2555 days"),
        check("archive KMS input", isinstance(inputs.get("kms_key_arn"), str)
              and bool(inputs["kms_key_arn"]),
              "bucket encryption points to a KMS key input (may be a render mock)"),
        check("archive delivery principals",
              isinstance(principals, list)
              and all(isinstance(value, str) for value in principals)
              and set(principals)
              == {"cloudtrail.amazonaws.com", "delivery.logs.amazonaws.com"},
              "CloudTrail and delivery service principals configured"),
    ]


def kms_checks(config: dict[str, Any]) -> list[Check]:
    inputs = inputs_of(config)
    return [check("archive key safeguards",
                  inputs.get("is_enabled") is True
                  and inputs.get("enable_key_rotation") is True
                  and inputs.get("bypass_policy_lockout_safety_check") is False
                  and inputs.get("deletion_window_in_days") == 30,
                  "key enabled, rotation on, lockout safety on, 30-day deletion window")]


def cloudtrail_checks(config: dict[str, Any], archive: dict[str, Any] | None) -> list[Check]:
    inputs = inputs_of(config)
    selectors = inputs.get("event_selectors")
    management_events = (
        isinstance(selectors, list) and len(selectors) == 1
        and isinstance(selectors[0], dict)
        and selectors[0].get("read_write_type") == "All"
        and selectors[0].get("include_management_events") is True
    )
    results = [
        check("CloudTrail capture", inputs.get("enable_logging") is True
              and inputs.get("is_multi_region_trail") is True
              and inputs.get("include_global_service_events") is True
              and management_events,
              "active multi-Region trail captures global and all management events"),
        check("CloudTrail delivery settings",
              inputs.get("create_s3_bucket") is False
              and inputs.get("s3_key_prefix") == "cloudtrail"
              and inputs.get("enable_cloudwatch_logs") is True
              and inputs.get("cloudwatch_logs_retention_days") == 365,
              "external archive with cloudtrail prefix and 365-day CloudWatch Logs"),
        check("CloudTrail key ownership", inputs.get("create_kms_key") is True,
              "Security stack creates its own trail KMS key"),
    ]
    if archive is None:
        results.append(Check("CloudTrail archive destination", "SKIP",
                             "archive stack could not be rendered"))
    else:
        bucket_name = inputs_of(archive).get("bucket_name")
        results.append(check("CloudTrail archive destination",
                             isinstance(bucket_name, str) and bool(bucket_name)
                             and inputs.get("s3_bucket_name") == bucket_name,
                             "trail destination matches the Log Archive bucket"))
    return results


def policy_checks(root: Path) -> list[Check]:
    results = []
    for relative in POLICIES:
        path = root / relative
        try:
            document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            results.append(Check(relative, "FAIL", f"cannot read valid JSON: {type(exc).__name__}"))
            continue
        statements = document.get("Statement") if isinstance(document, dict) else None
        valid = (isinstance(document, dict)
                 and document.get("Version") == "2012-10-17"
                 and isinstance(statements, list) and bool(statements)
                 and all(isinstance(item, dict) and item.get("Effect") == "Deny"
                         and ("Action" in item or "NotAction" in item)
                         and "Resource" in item for item in statements))
        results.append(check(relative, valid, "valid deny-only SCP document with statements"))
        if not valid or not isinstance(statements, list):
            continue
        actions = {
            action
            for statement in statements
            for action in (statement.get("Action") if isinstance(statement.get("Action"), list)
                           else [statement.get("Action")])
            if isinstance(action, str)
        }
        if relative.endswith("deny-create-iam-user.json"):
            results.append(check("IAM user policy actions",
                                 {"iam:CreateUser", "iam:CreateAccessKey"} <= actions,
                                 "denies IAM user and access-key creation"))
        elif relative.endswith("deny-disable-cloudtrail.json"):
            results.append(check("CloudTrail policy actions",
                                 {"cloudtrail:StopLogging", "cloudtrail:DeleteTrail"} <= actions,
                                 "denies stopping or deleting trails (document only)"))
        else:
            region_rules = [statement for statement in statements
                            if "NotAction" in statement]
            allowed = [statement.get("Condition", {}).get("StringNotEquals", {})
                       .get("aws:RequestedRegion") for statement in region_rules
                       if isinstance(statement.get("Condition"), dict)
                       and isinstance(statement["Condition"].get("StringNotEquals"), dict)]
            results.append(check("sandbox region policy",
                                 ["us-east-1", "us-west-2"] in allowed,
                                 "deny outside the policy's approved us-east-1/us-west-2 set"))
    return results


def render_stack(executable: str, path: Path, timeout: float) -> dict[str, Any]:
    completed = subprocess.run(
        [executable, "render", "--json", "--no-auto-init", "--no-color",
         "--log-level", "error", "--working-dir", str(path.parent)],
        cwd=path.parent, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False,
    )
    if completed.returncode:
        # Terragrunt diagnostics may contain inputs or environment values.
        raise ValueError(f"render exited {completed.returncode}; inspect {path} with Terragrunt")
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"render produced invalid JSON for {path}") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("inputs"), dict):
        raise ValueError(f"render omitted inputs for {path}")
    return parsed


def verify(root: Path, executable: str, timeout: float) -> tuple[list[Check], int]:
    results = policy_checks(root)
    paths = {name: root / relative for name, relative in STACKS.items()}
    available = {name: path.is_file() for name, path in paths.items()}
    for name, exists in available.items():
        results.append(check(f"{name} file", exists, f"required file: {STACKS[name]}"))

    resolved_executable = shutil.which(executable)
    if resolved_executable is None:
        results.append(Check("Terragrunt executable", "FAIL", f"cannot find: {executable}"))
        for name in STACKS:
            results.append(Check(f"{name} configuration", "SKIP", "Terragrunt unavailable"))
        return results, EXIT_TOOL

    rendered: dict[str, dict[str, Any]] = {}
    tool_error = False
    for name, path in paths.items():
        if not available[name]:
            results.append(Check(f"{name} configuration", "SKIP", "stack file missing"))
            continue
        try:
            rendered[name] = render_stack(resolved_executable, path, timeout)
        except subprocess.TimeoutExpired:
            results.append(Check(f"{name} render", "FAIL", f"Terragrunt timed out after {timeout:g}s"))
            tool_error = True
        except OSError as exc:
            results.append(Check(f"{name} render", "FAIL",
                                 f"cannot launch Terragrunt: {type(exc).__name__}"))
            tool_error = True
        except ValueError as exc:
            results.append(Check(f"{name} render", "FAIL", str(exc)))
        else:
            results.append(Check(f"{name} render", "PASS", "Terragrunt configuration rendered locally"))

    validators = {
        "sandbox GuardDuty": lambda c: guardduty_checks(c, sandbox=True),
        "Security GuardDuty": lambda c: guardduty_checks(c, sandbox=False),
        "Security CloudTrail": lambda c: cloudtrail_checks(c, rendered.get("Log Archive bucket")),
        "Log Archive bucket": archive_checks,
        "Log Archive KMS": kms_checks,
    }
    for name, validator in validators.items():
        if name in rendered:
            results.extend(validator(rendered[name]))
        else:
            results.append(Check(f"{name} inputs", "SKIP", "stack could not be rendered"))

    results.extend([
        Check("AWS deployed posture", "SKIP", "configuration-only run; no AWS API calls"),
        Check("CloudTrail log-file validation", "SKIP",
              "module implementation and deployed trail are outside this repository"),
        Check("cross-account archive policy", "SKIP",
              "external bucket/KMS policy readiness needs approved account IDs and live evidence"),
        Check("SCP attachments", "SKIP",
              "policy JSON alone cannot establish target attachment or effective policy"),
    ])
    return results, (EXIT_TOOL if tool_error else
                     EXIT_CONFIG if any(item.status == "FAIL" for item in results) else EXIT_OK)


def positive_timeout(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a positive number") from exc
    if not 0 < number < float("inf"):
        raise argparse.ArgumentTypeError("timeout must be finite and positive")
    return number


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the configured GuardDuty, CloudTrail, archive, and SCP baseline with local Terragrunt renders.",
        epilog="Exit: 0 checks passed (live posture unverified); 1 configuration failed; "
               "2 invalid input; 3 Terragrunt unavailable/failed to launch; 130 interrupted.",
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2],
                        help="repository root (default: derived from this script)")
    parser.add_argument("--terragrunt", default="terragrunt",
                        help="Terragrunt executable name or path (default: terragrunt)")
    parser.add_argument("--timeout", type=positive_timeout, default=90.0,
                        help="per-stack render timeout in seconds (default: 90)")
    parser.add_argument("--json", action="store_true", help="emit a JSON report for CI")
    args = parser.parse_args(list(argv) if argv is not None else None)
    root = args.root.expanduser().resolve()
    if not root.is_dir() or not (root / "live").is_dir() or not (root / "policies/scp").is_dir():
        parser.error(f"not a repository root with live/ and policies/scp/: {root}")
    try:
        results, code = verify(root, args.terragrunt, args.timeout)
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return EXIT_INTERRUPTED
    if args.json:
        print(json.dumps({"exit_code": code, "checks": [asdict(item) for item in results]}, indent=2))
    else:
        for item in results:
            print(f"[{item.status}] {item.name}: {item.detail}")
        print(f"Configuration result: {'PASS' if code == EXIT_OK else 'FAIL'} "
              "(deployed AWS posture unverified)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
