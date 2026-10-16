# Security Policy

This policy defines the security requirements for `platform-live-infra`, the
live infrastructure repository for composing, reviewing, and operating
production cloud environments. It applies to repository changes and to the
deployment processes that consume them.

## Scope

The security scope includes:

- Terraform and Terragrunt configuration, provider settings, and module
  references;
- environment, account, and Region composition;
- deployment workflows, approvals, and CI/CD authentication;
- remote-state configuration, locking, retention, and recovery;
- IAM, KMS, CloudTrail, GuardDuty, SCP, network, and other policy files;
- operational verification, drift detection, backup, and incident response;
- scripts, tests, toolchain definitions, dependencies, and repository
  automation.

Reusable infrastructure modules may be maintained in a separate repository.
This repository is responsible for live composition, environment context,
deployment authorization, state handling, change safety, and verification of
the resulting infrastructure.

## Supported Versions

Support is provided for the latest approved repository state and for approved
environment or stack baselines derived from it. When immutable tags or
releases are adopted, they serve as audit and rollback references; this policy
does not prescribe a tag format.

Older baselines are not guaranteed to receive fixes. Emergency remediation may
be issued for actively exploited or otherwise high-impact vulnerabilities
regardless of baseline age when operational risk requires it.

## Reporting a Vulnerability

**Do not disclose vulnerabilities through public issues, pull requests,
discussions, commits, or other public channels.**

Reports should contain enough information to reproduce and assess the issue:

- affected path, stack, workflow, or configuration;
- affected commit, baseline, environment, account, or Region, when known;
- reproduction steps or a minimal proof of concept;
- security impact, exploitability, and potential blast radius;
- relevant sanitized logs or screenshots;
- a suggested mitigation, if available.

Do not submit credentials, tokens, private keys, unredacted Terraform state,
sensitive plan files, account identifiers, role ARNs, bucket names, endpoints,
confidential logs, or customer data. Use sanitized examples and provide
high-sensitivity material only through an approved channel.

## Private Reporting Channel

Security vulnerabilities must be reported exclusively through
[GitHub private vulnerability reporting](../../security/advisories/new).
Public issues, pull requests, discussions, commits, or other public channels
must not be used for vulnerability reporting.

The repository's current sole maintainer is responsible for monitoring this
channel and ensuring that submitted reports remain confidential. If additional
maintainers are appointed, access to vulnerability reports must be granted
only to maintainers who require it for triage, remediation, or coordinated
disclosure.

Changes in repository maintainership must preserve the confidentiality and
continuity of the reporting process. GitHub private vulnerability reporting
must remain the authoritative reporting channel, and no public channel may be
used as a fallback. If the private reporting feature is temporarily
unavailable, reporters should retain the report securely and submit it after
the channel becomes available.

### Optional OpenPGP Encryption

GitHub Private Vulnerability Reporting does not natively encrypt or
decrypt reports using OpenPGP.

For highly sensitive details, you may encrypt the report locally with
the OpenPGP public key below and paste the resulting ASCII-armored
ciphertext into the private vulnerability report. The repository
maintainer will decrypt it outside GitHub.

Do not send the private key through GitHub or include it in the report.

-----BEGIN PGP PUBLIC KEY BLOCK-----

mDMEamMUPxYJKwYBBAHaRw8BAQdAgAcdLy/M0GLL3EHbP5EPGwNXl8UgSIztERBU
r2mwGmG0Lk1haGRpYXIgRmFzemluZmFyIDxtYWhkaWFyZmFyemluZmFyQGdtYWls
LmNvbT6IrwQTFgoAVxYhBKt6PCFgiSj2GbU2yPUCg16p8oKCBQJqYxQ/GxSAAAAA
AAQADm1hbnUyLDIuNSsxLjEyLDIsMQIbAwULCQgHAgIiAgYVCgkICwIEFgIDAQIe
BwIXgAAKCRD1AoNeqfKCggomAP9D4OArxt89hc7uZ8a7kmF0v9MEwJPstT1aFZUw
YyVuCQEAkJPzixGf46QfDpnXMug2+39ch5sozX/XTZQn0wD2WAQ=
=uhO9  
-----END PGP PUBLIC KEY BLOCK-----

Key fingerprint:

AB7A 3C21 6089 28F6 19B5 36C8 F502 835E A9F2 8282

Please verify the fingerprint through an independent channel before using the key to encrypt highly sensitive information.

## Severity Classification and Response Targets

Severity is assessed primarily with CVSS v3.1 and adjusted for practical
exploitability, required privileges, exposure, affected environments, data
sensitivity, and infrastructure blast radius.

| Severity | CVSS v3.1 score | Initial acknowledgement | Remediation target |
| --- | --- | --- | --- |
| Critical | 9.0–10.0 | Within 24 hours | Within 7 days |
| High | 7.0–8.9 | Within 48 hours | Within 30 days |
| Medium | 4.0–6.9 | Within 5 business days | Within 60 days |
| Low | 0.1–3.9 | Within 7 business days | Within 90 days |
| Informational | 0.0 | Within 7 business days | No mandatory target |

These are operational targets, not contractual service levels. Severity and
timelines may change after validation, newly discovered impact, active
exploitation, upstream dependencies, or required emergency controls.

## Bug Bounty Policy

This project does not operate an official paid bug bounty program. Good-faith
research submitted through coordinated vulnerability disclosure is welcome;
no payment, reward, or other compensation is promised.

Researchers must avoid unauthorized access, data modification or exfiltration,
service degradation, denial-of-service testing, social engineering, phishing,
credential attacks, and testing that could affect a live account or Region.
Stop testing and report immediately if sensitive data is encountered.

## Security Baseline

Production infrastructure must meet the following baseline. Service-specific
implementation may vary, but every exception requires documented approval,
scope, owner, rationale, compensating controls, and review date.

### Encryption and key management

- Persistent data and remote state must be encrypted at rest.
- Customer-managed KMS keys must be used where required by data sensitivity,
  service capability, or compliance obligations.
- Key policies must separate administration, usage, and service access and
  must be reviewed for least privilege.
- Rotation, deletion windows, recovery, grants, and lockout-safety controls
  must be deliberate, documented, and tested.

### Audit, detection, and centralized logging

- CloudTrail must provide the approved account, organization, management-event,
  global-service, and Region coverage.
- GuardDuty must be enabled for every approved account and Region within the
  defined security boundary, with clear administrator ownership.
- Audit and security-service logs must be delivered to private, encrypted,
  access-controlled centralized storage with approved retention and recovery.
- Logging and detection failures, unexpected disablement, and delivery gaps
  must generate actionable alerts.

### Preventive guardrails and access

- SCPs and equivalent preventive guardrails must be narrowly scoped, rendered,
  reviewed, tested, and approved before attachment or expansion.
- IAM permissions and trust policies must follow least privilege and use
  explicit principals, resources, actions, conditions, and boundaries where
  appropriate.
- Break-glass access must remain possible, controlled, monitored, and tested.

### Network and public exposure

- Account, organization, and Region boundaries must be explicit security
  boundaries, not implicit assumptions.
- Network segmentation, routing, ingress, egress, security groups, network
  ACLs, and administrative paths must be reviewed for least exposure.
- Services and storage must default to private access. Any public endpoint,
  ingress rule, or internet-facing resource requires explicit risk review.

### Ownership, tagging, backup, and recovery

- Resources must carry mandatory ownership, environment, data-classification,
  and cost or service tags where supported.
- Owner must document lifecycle, retention, backup coverage, restore testing,
  recovery objectives, and replacement or deletion consequences.
- Security monitoring, alert routing, and on-call responsibility must be
  defined for production services.

## Infrastructure Deployment Security

All mutating infrastructure operations must be authorized, reviewable, and
auditable.

- Pull requests must receive required peer review and automated checks.
- Branch protection and CODEOWNERS must cover security-sensitive
  configuration, policies, workflows, state settings, and authentication.
- A plan must be generated from the reviewed commit and inspected before apply.
- Apply must use the exact approved plan; stale or changed plans must be
  rejected and regenerated.
- Production deployment must use a protected environment with explicit manual
  approval and separation between planning and applying privileges.
- Concurrency controls must prevent conflicting applies to the same stack or
  state.
- Account, Region, environment, stack, provider, and module-version context
  must be asserted before every plan and apply.
- Direct local production apply is prohibited except under an approved
  break-glass procedure that records identity, reason, scope, approval, and
  outcome.
- Every mutating action must retain an audit trail sufficient to reconstruct
  who authorized it, what was applied, and where.
- Out-of-band changes must be prevented where practical and detected through
  audit logs, read-only plans, or equivalent controls.

CI/CD must use short-lived federated credentials, preferably GitHub OIDC,
with narrowly scoped repository, environment, branch, or tag trust. Long-lived
cloud credentials must not be committed, embedded in workflows, or stored in
unapproved locations.

## State and Secrets Management

- Terraform state must use an approved remote backend with encryption at rest,
  state locking or equivalent concurrency control, least-privilege access,
  versioning, retention, and recovery.
- State access must be limited to approved operators and automation. State
  contents, backend details, and plan artifacts must be treated as sensitive
  operational data.
- Secrets must be supplied through an approved secrets manager or approved
  GitHub environment secrets, never through source files or unprotected
  variables.
- Logs, plans, test output, and artifacts must mask or omit sensitive values.
- Terraform state, plans, credentials, tokens, passwords, private keys, and
  secret variable files must not be committed or publicly uploaded.
- Exposed credentials must be revoked or rotated immediately, investigated
  through authoritative audit data and a documented forensic review, and
  removed from affected artifacts and history where practicable.

## Cloud Authentication and Access Control

- Human and machine access must be federated through approved identity
  controls and protected with MFA or equivalent assurance.
- CI must use short-lived credentials and narrowly scoped trust, preferably
  through GitHub OIDC.
- Read-only validation, planning, applying, and break-glass recovery must use
  separate roles or equivalent permission boundaries.
- Trust policies must restrict approved repositories, environments, branches or
  tags, accounts, Regions, and audiences.
- Permissions must be least privilege and reviewed periodically, including
  unused grants, service roles, and emergency access.
- Emergency access must be time-bound, approved, logged, and reviewed after
  use.

## Automated Security Validation

Every change must pass applicable automated validation before approval,
including:

- Terraform/Terragrunt formatting, parsing, and validation;
- IaC misconfiguration scanning;
- Terraform linting;
- secret and private-key scanning;
- GitHub Actions workflow and policy-file validation;
- dependency and supply-chain scanning;
- pre-commit validation where configured.

Checkov, Trivy, TFLint, Gitleaks, and equivalent tools are acceptable
implementation choices. Findings must be fixed or suppressed through a
documented exception with an owner, rationale, tracking reference, and expiry.
Scanner exclusions must not conceal material production risk.

## Dependency and Supply Chain Security

- Terraform providers, Terragrunt, modules, GitHub Actions, scanners, and
  other dependencies must be pinned or otherwise constrained to trusted
  versions.
- Module sources and version changes must be reviewed for provenance,
  compatibility, permissions, and security impact.
- GitHub Actions should use trusted, reviewed versions or immutable references
  where practical, with least-privilege workflow permissions.
- Dependency updates must arrive through pull requests and pass required
  validation and deployment-risk review.
- Automated updates must not bypass required reviews, protected environments,
  or production approvals.

## Drift Detection and Incident Response

Scheduled read-only plans or an equivalent mechanism must detect unauthorized
or unexpected infrastructure changes. Alerts must be routed to the accountable
infrastructure owner and investigated with CloudTrail and other authoritative
platform logs.

For a live-infrastructure security incident:

1. Contain the risk without destroying evidence.
2. Revoke or rotate exposed credentials and restrict affected access.
3. Determine affected accounts, Regions, stacks, resources, and data.
4. Preserve state versions, plans, workflow records, and cloud audit logs in
   protected storage.
5. Restore or roll back using an approved recovery procedure.
6. Complete root-cause analysis, corrective actions, and follow-up monitoring.

## Vulnerability Disclosure

This project follows Coordinated Vulnerability Disclosure. Researchers and
maintainers must not publicly disclose a vulnerability, proof of concept,
affected account, or sensitive configuration before validation and a reasonable
opportunity to remediate.

After remediation or an effective mitigation, maintainers may publish an
advisory describing affected scope, severity, impact, remediation guidance,
and researcher credit where appropriate. If a report remains unresolved, the
parties should agree on a disclosure timeline; a 90-day target may be used as
an operational guideline, subject to active exploitation, safety, legal, and
dependency considerations.

## Policy Governance

The security policy must be reviewed periodically and after material changes to
cloud architecture, deployment workflows, authentication, state management,
security ownership, or vulnerability-reporting channels.

Policy exceptions require documented approval, an accountable owner,
compensating controls, an expiry or review date, and a record of closure.
Changes to this policy must receive the same review required for other
security-sensitive repository changes.
