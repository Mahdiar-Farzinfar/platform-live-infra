"""Focused regression tests for the read-only security baseline decision logic."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("verify-security-baseline.py")
SPEC = importlib.util.spec_from_file_location("security_baseline", SCRIPT)
assert SPEC and SPEC.loader
import sys

baseline = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = baseline
SPEC.loader.exec_module(baseline)


class SecurityBaselineTests(unittest.TestCase):
    def test_guardduty_reports_disabled_runtime_agent(self) -> None:
        features = {name: {"enabled": True} for name in baseline.FEATURES}
        features["RUNTIME_MONITORING"]["additional_configuration"] = {
            name: True for name in baseline.RUNTIME_AGENTS
        }
        features["RUNTIME_MONITORING"]["additional_configuration"]["EC2_AGENT_MANAGEMENT"] = False
        config = {"inputs": {
            "enabled": True, "finding_publishing_frequency": "FIFTEEN_MINUTES",
            "detector_features": features,
            "organization_admin": {"delegate_admin": False,
                                   "manage_org_configuration": False, "auto_enable": "NEW"},
            "organization_features": {}, "publishing_destination": None,
        }}
        checks = baseline.guardduty_checks(config, sandbox=True)
        self.assertEqual({c.name for c in checks if c.status == "FAIL"},
                         {"sandbox runtime agents"})

    def test_cloudtrail_destination_uses_rendered_archive_name(self) -> None:
        trail = {"inputs": {
            "enable_logging": True, "is_multi_region_trail": True,
            "include_global_service_events": True,
            "event_selectors": [{"read_write_type": "All", "include_management_events": True}],
            "create_s3_bucket": False, "s3_key_prefix": "cloudtrail",
            "enable_cloudwatch_logs": True, "cloudwatch_logs_retention_days": 365,
            "create_kms_key": True, "s3_bucket_name": "wrong-bucket",
        }}
        checks = baseline.cloudtrail_checks(trail, {"inputs": {"bucket_name": "archive"}})
        self.assertEqual([c.status for c in checks], ["PASS", "PASS", "PASS", "FAIL"])
        self.assertEqual(baseline.cloudtrail_checks(trail, None)[-1].status, "SKIP")

    def test_policy_rejects_json_with_no_statements(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in baseline.POLICIES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"Version": "2012-10-17", "Statement": []}),
                                encoding="utf-8")
            self.assertTrue(all(c.status == "FAIL" for c in baseline.policy_checks(root)))

    def test_policy_rejects_deny_document_without_expected_action(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in baseline.POLICIES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"Version": "2012-10-17", "Statement": [
                    {"Effect": "Deny", "Action": ["s3:DeleteBucket"], "Resource": "*"}
                ]}), encoding="utf-8")
            checks = baseline.policy_checks(root)
            self.assertEqual([c.status for c in checks if c.name == "IAM user policy actions"],
                             ["FAIL"])
            self.assertEqual([c.status for c in checks if c.name == "CloudTrail policy actions"],
                             ["FAIL"])
            self.assertEqual([c.status for c in checks if c.name == "sandbox region policy"],
                             ["FAIL"])

    def test_render_invokes_only_local_read_command_and_hides_failure_output(self) -> None:
        path = Path("/repo/live/stack/terragrunt.hcl")
        with patch.object(baseline.subprocess, "run", return_value=subprocess.CompletedProcess(
            [], 1, "secret stdout", "secret stderr")) as run:
            with self.assertRaisesRegex(ValueError, "render exited 1") as error:
                baseline.render_stack("terragrunt", path, 10)
        self.assertNotIn("secret", str(error.exception))
        args, kwargs = run.call_args
        self.assertEqual(args[0][:4], ["terragrunt", "render", "--json", "--no-auto-init"])
        self.assertEqual(kwargs["cwd"], path.parent)
        self.assertTrue(kwargs["capture_output"])
        self.assertNotIn("shell", kwargs)


if __name__ == "__main__":
    unittest.main()
