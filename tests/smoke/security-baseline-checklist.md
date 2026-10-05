# Security Baseline Review Checklist

Use this checklist for source review, deployment readiness, and post-apply evidence
collection. Mark each item **Pass**, **Fail**, **Not assessed**, or **Not applicable**.
Record the source revision, target stack/account/Region using approved internal
records, reviewer, date, evidence location, result, and follow-up for each applicable
check. Do not put account identifiers, ARNs, credentials, state details, or sensitive
outputs in this document or public review comments.

## Evidence and status

Repository configuration and tests show intended configuration; they do not prove that a change was deployed or is effective in AWS. Keep these evidence types distinct:

- **Source/configuration:** checked-in policy JSON, Terragrunt inputs, catalogs, and workflow definitions.
- **CI execution:** a specific workflow run and its logs or summary, tied to a source revision. A configured workflow is not evidence it ran successfully or is a required merge gate.
- **Cloud runtime:** approved read-only observations of the target account and Region after deployment.
- **Attestation:** reviewer/operator confirmation of checks that automation cannot perform.

Use **Not assessed** when evidence has not been collected. Use **Fail** when collected evidence contradicts an expected control. For unavailable, incomplete, or placeholder configuration, record the relevant limitation rather than treating a local configuration pass as deployed success.

## Checklist

### Identity and access

- [ ] Review the GitHub OIDC provider and role trust configuration in
  [`github-oidc`](../../live/foundation/management/us-east-1/github-oidc/terragrunt.hcl).
  Confirm approved repository/subject restrictions and permissions in the resolved
  module and deployed IAM policy. This repository configures a role with an apply-
  policy placeholder; it does not establish that permissions are least-privilege or
  that the role is deployed.
- [ ] Confirm human and emergency access boundaries and credential handling through the approved account/IAM review. The live configuration alone does not establish human-access controls.
- [ ] Review [`deny-create-iam-user.json`](../../policies/scp/deny-create-iam-user.json): it denies IAM user, access-key, and login-profile creation actions with exceptions for named emergency role patterns. Verify the policy is attached and effective before claiming enforcement. The management SCP stack currently has `target_ids = []`; it creates the policy without attaching it.
- [ ] Review workload IAM role trust and permission policies against the intended read-only validation scope where applicable; check the inventory's readiness and post-deployment items for the selected stack.

### Organization and account guardrails

- [ ] Review [`restrict-regions.json`](../../policies/scp/restrict-regions.json) and its `NotAction`, requested-region, global-resource, and emergency-role conditions. Confirm allowed Regions and necessary exceptions against approved operational requirements.
- [ ] Confirm the sandbox attachment stack targets only the intended account after approved catalog values are populated. Its target is conditional on an account ID; verify actual attachment and effective policy in AWS. A policy file or successful local render alone does not show attachment.
- [ ] Review [`deny-disable-cloudtrail.json`](../../policies/scp/deny-disable-cloudtrail.json),
  including action/resource scope and emergency/security-automation exceptions. This
  policy is present in the repository, but the configured management SCP stack selects
  the IAM-user policy and has no target attachments. Do not claim this CloudTrail SCP
  is deployed or effective from its presence in source control.
- [ ] Verify account separation and deployment prerequisites against [`deployment-order.yaml`](../../inventory/deployment-order.yaml). Account catalog values include placeholders; do not deploy until approved identifiers and target context are verified.

### Audit logging and archive

- [ ] Confirm the Security CloudTrail configuration enables logging, a multi-Region trail, global service events, and all management events, and references the Log Archive bucket dependency. Verify the deployed trail, destination, and delivery in AWS.
- [ ] Confirm the archive bucket configuration enables Object Lock in COMPLIANCE mode for 2,555 days, disables force-destroy, and configures the KMS key input and CloudTrail delivery principals. Verify bucket policy, encryption, Object Lock, retention, and delivery at runtime.
- [ ] Confirm the Security trail's CloudWatch Logs integration and configured 365-day retention. This setting is distinct from archive retention.
- [ ] Do not infer CloudTrail log-file validation, organization-wide trail coverage, or effective cross-account delivery policy from the local smoke checks. The smoke verifier explicitly reports log-file validation and cross-account archive-policy readiness as skipped; module internals and runtime state are outside its checks.

### Threat detection

- [ ] Confirm Security and sandbox GuardDuty configuration enables the detector, all six configured protection features, the configured runtime agent management, and 15-minute finding publication cadence. Check the selected account and Region at runtime.
- [ ] Verify organization auto-enable behavior and enrollment against the configured ownership split: the Security stack manages organization configuration; sandbox configuration does not. Delegated-administrator registration is documented as an external management-account operation without a separate live stack.
- [ ] Review actual findings and finding delivery separately. The configuration smoke check does not query findings or prove threat-free status; sandbox findings export is not configured by the reviewed stack.

### Encryption, keys, and state

- [ ] Verify the Log Archive KMS key is enabled, automatic rotation is enabled, policy lockout safety is retained, and the configured deletion window is 30 days. Review key policy and approved cross-account service access; additional principals are intentionally not configured in the live KMS inputs.
- [ ] Verify the archive bucket uses the KMS key and its retention/deletion safeguards at runtime. The smoke verifier checks rendered inputs, not actual encryption or key accessibility.
- [ ] For normal stacks, review [`remote-state.hcl`](../../live/_envcommon/remote-state.hcl): S3 backend, hierarchy-derived key, DynamoDB lock table, encryption, and KMS key input. Backend values are placeholders/unresolved until approved bootstrap outputs or catalog metadata are supplied. Do not expose backend identifiers or state contents.
- [ ] Review plan and state artifacts for access restrictions and sensitive-data exposure under repository change controls. Local plans are advisory and may contain sensitive data.

### CI/CD and change control

- [ ] Review applicable workflow configuration and the exact run tied to the change. [`validate.yml`](../../.github/workflows/validate.yml) and [`security-scan.yml`](../../.github/workflows/security-scan.yml) define repository checks; inspect their triggers, conditions, permissions, and results. Their presence does not prove external branch protection or required status checks.
- [ ] [`plan.yml`](../../.github/workflows/plan.yml) performs pull-request planning metadata validation and limits cloud-capable plan behavior to trusted `main` runs. Treat plans as advisory; this workflow does not implement the repository's described saved-plan/apply approval process.
- [ ] [`apply.yml`](../../.github/workflows/apply.yml) is a manually dispatched safe-skip workflow: it runs with `APPLY=false`, supplies no AWS credentials, and does not deploy infrastructure. Do not use its success as evidence of an apply.
- [ ] [`post-apply-verify.yml`](../../.github/workflows/post-apply-verify.yml) is manually dispatched for an inventory stack. Its helper runs the repository-wide configuration smoke and reports inventory runtime checks as pending; it does not verify deployed AWS posture.
- [ ] [`drift-detection.yml`](../../.github/workflows/drift-detection.yml) provides scheduled/manual read-only drift scans for remote-state stacks when configured identity and state access are available. Preserve the specific run output; it does not replace targeted post-deployment checks.
- [ ] Confirm approved reviews, deployment environment protections, OIDC permissions, artifact controls, and concurrency/state locking in the actual repository settings and run context. Those external settings cannot be established from workflow files alone.

### Verification and monitoring

- [ ] Run `task verify:security-baseline` only in an environment with the required local Terragrunt executable. It parses the three SCP JSON documents and locally renders five named stacks, then checks selected rendered GuardDuty, CloudTrail, archive, and KMS inputs. It makes no AWS API calls and uses no AWS credentials or AWS-specific environment variables by design.
- [ ] Interpret smoke exit codes accurately: `0` means evaluated configuration
  checks passed, not deployed posture; `1` means configuration failure; `2` means
  invalid CLI/repository input; `3` means Terragrunt unavailable or unable to run;
  `130` means interrupted. Output contains check statuses/details; `--json` emits a
  JSON report. Render diagnostics are reduced to avoid printing potentially sensitive
  input values.
- [ ] The verifier's scope does not establish policy attachment/effect, deployed AWS configuration, CloudTrail log-file validation, archive cross-account policy readiness, GuardDuty findings, or effective human access. It uses local Terragrunt renders and may use configured render mocks; it is not a general-purpose cloud scanner.
- [ ] For post-apply review, use the inventory's `post_deploy_checks` and collect separate live evidence. The post-apply helper marks those checks pending and reports the configuration smoke result; a passing smoke run is not runtime validation.
- [ ] Drift results are evidence only for the stacks actually scanned at that time. Investigate operational errors separately from detected drift.

## Verification map

| Control | Authoritative repository evidence | Verification mechanism | Additional runtime evidence |
| --- | --- | --- | --- |
| SCP content and configured attachment targets | [`policies/scp/`](../../policies/scp/), management SCP and sandbox attachment Terragrunt files | JSON parsing and local smoke assertions; review configured target IDs | AWS policy attachment and effective-policy evidence for intended targets |
| CloudTrail and archive configuration | Security CloudTrail, Log Archive bucket, and KMS Terragrunt files | Local smoke assertions over rendered inputs | Trail status, delivery, encryption, bucket policy, Object Lock and retention |
| GuardDuty configuration | Security and sandbox baseline Terragrunt files | Local smoke assertions over rendered inputs | Detector, feature, enrollment, Region, and organization configuration observations |
| GitHub OIDC and IAM | Management OIDC and workload role stack files | Source review, workflow execution evidence, and inventory checks | IAM trust, attached permissions, session and access observations |
| Remote state | [`remote-state.hcl`](../../live/_envcommon/remote-state.hcl), bootstrap configuration | Configuration review and approved state-access/drift workflow | Backend encryption, access, locking, and state access evidence |
| Change and deployment controls | Workflow files, [`CONTRIBUTING.md`](../../CONTRIBUTING.md), [`CODEOWNERS`](../../CODEOWNERS) | Specific CI run plus reviewer/operator attestation | Repository/environment protection settings and approved deployment record |

## Failure handling

When a check fails, preserve the check name, source revision, workflow/run reference,
and sanitized output in the approved evidence location. Trace the failure to the
relevant source configuration, policy, workflow, or inventory entry; consult the
[live infrastructure guide](../../live/README.md), [test guidance](../README.md), and
[contribution process](../../CONTRIBUTING.md). Check the configured stack owner in
[`stack-owners.yaml`](../../inventory/stack-owners.yaml). Remediate through the
repository's normal reviewed change process, then rerun the affected validation and
collect fresh runtime evidence where required. If no remediation procedure is
documented, establish it through the normal ownership and change-management process.
Do not bypass review, weaken controls, suppress findings without documented
justification, or make unreviewed production changes.

## Limitations

This checklist does not prove complete security, replace continuous monitoring or
formal risk acceptance, or establish a compliance certification. Configuration checks
cannot validate runtime state without corresponding live evidence. Drift is only
assessed when the configured drift mechanism runs with access to the relevant remote-
state stacks. Update this checklist when relevant policies, modules, live
configuration, workflows, or verification code change. The reusable Terraform module
implementations are external to this repository, so source review here cannot
establish their internal behavior.

## Related documentation

- [Repository overview](../../README.md)
- [Security policy](../../SECURITY.md)
- [Contribution guidance](../../CONTRIBUTING.md)
- [Code ownership](../../CODEOWNERS)
- [Live infrastructure guide](../../live/README.md)
- [Workload configuration guide](../../live/workloads/README.md)
- [Test guidance](../README.md)
- [Deployment order](../../inventory/deployment-order.yaml)
- [Stack ownership](../../inventory/stack-owners.yaml)
- [Security baseline verifier](./verify-security-baseline.py)
- [Post-apply verifier](../../scripts/ci/verify-post-apply.py)
- [Validation workflow](../../.github/workflows/validate.yml)
- [Security scan workflow](../../.github/workflows/security-scan.yml)
- [Policy directory](../../policies/scp/)
