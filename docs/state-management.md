# State Management

## Purpose

Terraform state maps the configuration managed by Terraform to the objects it
tracks and supplies data used to calculate plans. Terragrunt selects and
composes the stack configuration that Terraform initializes and operates.
State can contain sensitive resource attributes, so access, locking, migration,
and evidence handling need explicit controls.

This document describes the checked-in state design and the repository's
bootstrap, migration, planning, and verification entry points for platform
engineers, operators, reviewers, and incident responders. It distinguishes
source configuration from CI execution and AWS runtime evidence. A configured
backend or successful static check does not prove that a backend exists, that a
workflow ran, or that deployed state is healthy.

## Scope and Non-Goals

The scope is the Terragrunt stacks under `live/`, including the special
`live/bootstrap/backend-bootstrap` stack and the foundation and workload
stacks. It covers intended local-to-remote bootstrap and state migration,
remote backend configuration, CI plan and drift behavior, and safe handling of
state-related operations.

This is not an AWS, Terraform, or Terragrunt manual and does not replace the
[bootstrap guide](bootstrap.md), the [deployment order](deployment-order.md),
incident-response procedures, or authorized change management. It does not
establish current AWS configuration, repository protection settings, or
operational readiness. The checked-in account and backend metadata are
unresolved in this checkout; normal remote backend initialization and bootstrap
apply are not ready to use until approved values are supplied through reviewed
configuration.

## State Architecture

`live/terragrunt.hcl` exposes shared catalog projections but defines neither a
provider nor a backend. Normal stack Terragrunt files include this root and
the shared provider, tagging, and remote-state layers. `account.hcl` and
`region.hcl` provide hierarchy context. The provider layer generates
`provider.tf`; the remote-state layer generates `backend.tf` with
`overwrite_terragrunt` behavior. These are generated files, not hand-edited
configuration.

The normal remote-state layer configures Terraform's S3 backend with
encryption enabled, a customer-managed KMS key, and a DynamoDB lock table. Its
state key is derived from the path relative to the Terragrunt include plus
`terraform.tfstate`. Account and Region directories remain in that hierarchy,
so separate stack paths yield separate keys. The code has no empty-value or
local-backend fallback for normal stacks. Backend bucket, backend Region, lock
table, and KMS key are read from the shared configuration projection; they are
not defined concretely in the checked-in catalogs. Do not infer or publish
these values from ambient identity or tool output.

The bootstrap stack is intentionally excluded from the remote-state include:
it uses local Terraform state while creating the backend. It has its own
generated AWS provider and requires explicit bootstrap configuration. Once the
backend is created and configuration is reviewed, the migration helper moves
selected consuming stacks using `terragrunt init -migrate-state`. The
bootstrap stack itself is not a normal consuming stack.

Terragrunt dependencies can read outputs from other stacks; the deployment
inventory defines ordering and readiness. This dependency behavior does not
merge states: each stack remains a separate state unit. Review
[`inventory/deployment-order.yaml`](../inventory/deployment-order.yaml) and
the individual stack configuration before operating on a dependency chain.

## Evidence and Control Boundaries

Use these evidence categories distinctly:

| Evidence | What it establishes | What it does not establish |
| --- | --- | --- |
| Source configuration | Intended backend, provider, key-generation, scripts, and workflow logic in a revision | Deployment, external GitHub settings, or current AWS runtime behavior |
| CI execution | Results of a specific workflow run and revision, including the outcome of the enforced required merge gate | That any separate operation was executed outside the recorded workflow run |
| Runtime evidence | Approved read-only AWS observations for a stated target and time | Future health or unobserved accounts/stacks |
| Operator record | Authorization, scope, and evidence collected for a maintenance action | A technical control unless independently implemented and verified |

The migration helper inspects backend metadata and checks the result of
`state pull`; this is evidence about that migration run, not a general backup or
disaster-recovery guarantee.

## Bootstrap, Migration, and Locking

### Backend creation

[`live/bootstrap/backend-bootstrap/terragrunt.hcl`](../live/bootstrap/backend-bootstrap/terragrunt.hcl)
selects the backend-bootstrap module and enables access logging, deletion
protection, and noncurrent-version retention inputs. Module implementation is
external to this repository, so these inputs alone do not prove deployed
bucket behavior. The root/shared configuration and catalogs currently lack
concrete backend-bootstrap metadata, and account IDs contain placeholders.
The bootstrap helper fails closed on unresolved values for apply.

[`scripts/bootstrap/01-create-backend.py`](../scripts/bootstrap/01-create-backend.py)
validates repository context and orchestrates Terragrunt; it does not itself
create AWS resources. Its default/`--plan` path initializes with
`--backend=false`, validates, and plans. `--dry-run` prints intended commands.
`--apply` performs the cloud mutation after interactive `yes`, or requires
`--yes` with `--non-interactive`; the script then runs apply with
`-auto-approve`. That prompt is not an authorization workflow. See
[`docs/bootstrap.md`](bootstrap.md) and the repository's
[execution policy](../README.md#infrastructure-execution-policy) before any
approved bootstrap exception.

### State migration

[`scripts/bootstrap/02-migrate-to-remote.py`](../scripts/bootstrap/02-migrate-to-remote.py)
discovers non-bootstrap stacks, supports explicit stack selection and include
or exclude filters, and reports local/remote classification. Its list, plan,
and dry-run modes do not perform the migration; dry-run does not make the
backups that actual migration makes. Actual migration validates configured
backend values, calls STS to check identity and Region context, inspects bucket
location, versioning, encryption and public-access-block settings and checks
the lock table. It prompts for confirmation (or requires `--yes` in
non-interactive mode), copies local state and Terraform metadata to the
repository-local `.bootstrap-backups` directory by default, runs
`terragrunt init -migrate-state`, then pulls state and checks backend metadata.
Backups contain sensitive state and must be protected and retained under the
approved maintenance procedure.

The helper uses a process lock to prevent two instances of itself from running
concurrently. It does not coordinate with Terraform, Terragrunt, or GitHub
Actions processes. Migration changes state and is not documented as atomic,
reversible, or automatically recoverable. On interruption, failure, or
verification error, retain local state and backups, prevent further operations
against the affected state, and escalate for owner review. Do not retry blindly.

### Locking and concurrency

The configured remote backend names a DynamoDB table for locking. Terraform
backend operations that take a state lock use the configured backend locking
mechanism; read-only workflows may deliberately disable Terraform locking.
Lock contention should be investigated by confirming the affected stack and
checking for active operator and workflow activity. The helper's own process
lock is not a Terraform state lock. Do not force-unlock as routine
troubleshooting; this repository documents no general force-unlock recovery
procedure.

The plan workflow serializes its trusted cloud plans with other runs of that
workflow. The drift workflow serializes its own runs. Those concurrency groups
are workflow-specific and do not serialize plan, drift, migration, and manual
operations against one another. The drift implementation explicitly passes
`-lock=false` to init and plan. Do not treat that scan or GitHub concurrency as
a substitute for state locking or cross-workflow coordination.

## State Operations

Commands below are repository-defined entry points. Apply and migration
require explicit authorization and a reviewed procedure. Commands that access
cloud state require the intended authorized identity and target configuration.

| Operation | Entry point | Classification and evidence |
| --- | --- | --- |
| Check local tools | `task verify-env` | Read-only local metadata/tool check; does not establish AWS access or backend health. |
| Render configuration | `task render:terragrunt TARGET=[REVIEWED_STACK_PATH]` | Local configuration inspection; rendering can expose values, so protect output. `TARGET` is required operator input. |
| Initialize for static validation | `task init TARGET=[REVIEWED_STACK_PATH]` | Uses `-backend=false`; repository task says it does not provision backend resources or migrate state. It is not remote-state validation. |
| Validate Terraform configuration | `task validate:terraform TARGET=[REVIEWED_STACK_PATH]` | Local validation after backend-disabled initialization; no cloud deployment evidence. |
| Create an advisory plan | `task plan TARGET=[REVIEWED_STACK_PATH]` | Planning; may read cloud and remote state with authorized credentials. Plans can contain sensitive data. `STRICT=1` makes plan errors fail rather than pass recognized placeholder/credential errors. |
| Bootstrap plan | `task bootstrap:create-backend -- --plan` | Planning in the local-state bootstrap stack. The current unresolved configuration prevents a usable deployment. |
| Inspect migration candidates | `task bootstrap:migrate-to-remote -- --list-stacks` or `--plan` | State inspection/classification; review the selected set. These modes do not establish backend readiness. |
| Migrate selected state | `task bootstrap:migrate-to-remote -- --migrate --stack [REVIEWED_STACK_PATH]` | State-changing. Placeholder is required operator input. Requires approved maintenance scope, verified target/identity, no concurrent operation, confirmation, and protected backups. |
| Detect drift | `task drift` | Read-only remote-state plan scan in inventory order. The Taskfile target invokes the drift script, which disables locking and reports clean, drift, or operational error. |
| Create backend | `task bootstrap:create-backend -- --apply` | Infrastructure-mutating. Controlled bootstrap exception only, after explicit authorization and plan review. |
| Apply normal stacks | `task apply TARGET=[REVIEWED_STACK_PATH] APPLY=true` | Infrastructure-mutating task path. The current checked-in GitHub apply workflow deliberately omits enabling apply and is a safe-skip workflow. |

The Taskfile defines `TARGET` scope for stack tasks and uses `TG_ARGS` for
Terragrunt arguments. Check `Taskfile.yml` before relying on wrapper behavior.
The read-only configuration smoke task (`task verify:security-baseline`) checks
rendered inputs; it does not query AWS or inspect Terraform state.

## Safe Operating Procedure

1. Confirm the exact source revision, stack, account, Region, and approved
   operation. This is operator discipline, not a repository-enforced runtime
   check for every local command.
2. Run `task verify-env` and compare installed versions with
   [`tooling/.tool-versions`](../tooling/.tool-versions). This verifies local
   tooling only.
3. Inspect the stack's `account.hcl`, `region.hcl`, includes, and shared
   backend/provider layers. Verify target identity through the approved
   procedure before any cloud-aware operation.
4. Confirm no workflow, operator, or other process is operating on the same
   state. Repository workflow concurrency does not cover every execution path.
5. Use repository-defined validation and planning entry points. Review all
   plan output securely. Local plans are advisory and do not authorize apply.
6. For an approved state or infrastructure mutation, follow its specific
   documented change/maintenance procedure, authorization, and confirmation
   requirements. Do not infer permission from a successful validation or
   workflow run.
7. Afterward, verify the operation using the procedure's read-only checks and
   record revision, target, run, result, and sanitized evidence. Never record
   state contents or secrets.

## CI/CD, Drift, and State Integrity

[`plan.yml`](../.github/workflows/plan.yml) gives pull requests a metadata and
inventory validation path without AWS credentials. Trusted `main` runs assume
a read-only identity using GitHub OIDC and execute advisory plans. The plan
script captures command output rather than publishing raw state or plans; the
workflow says results are not saved-plan artifacts, do not authorize apply,
and are not uploaded or commented on. Its workflow-level concurrency does not
cover the drift workflow or external operations.

[`drift-detection.yml`](../.github/workflows/drift-detection.yml) is executed
on a schedule or through manual dispatch against `main`. It assumes the
configured OIDC planning identity and invokes the repository-defined
`task drift` target. The checked-in `Taskfile` defines `drift` as the canonical
drift-detection task, and the CI workflow uses this same target, establishing
alignment between the documented repository entry point and the CI execution
path.

The `task drift` target invokes the drift-detection script. The script selects
remote-state stacks from the deployment inventory, validates provider lockfiles
and remote-state includes, and runs Terragrunt initialization followed by a
detailed-exitcode plan with `-lock=false`. Command output is held in memory,
and sanitized per-stack results are published to the GitHub Actions job
summary.

The process returns exit status `0` when no drift is detected, `1` when drift is
detected, and `2` when an operational error occurs. Accordingly, the workflow
provides a consistent, repository-defined mechanism for scheduled and
on-demand drift detection. Its results remain bounded by the stacks selected
for scanning and by the permissions and access available to that specific
workflow run; the scan does not prove that every resource is represented in
Terraform State or identify every possible out-of-band condition.

[`post-apply-verify.yml`](../.github/workflows/post-apply-verify.yml) is
manually dispatched for an inventory stack and revision. Its script runs a
repository-wide local configuration smoke test and reports inventory live
checks as pending. It does not verify deployed AWS posture. The checked-in
[`apply.yml`](../.github/workflows/apply.yml) intentionally uses a safe-skip
path without AWS credentials, so a successful run is not evidence of an apply.

[`validate.yml`](../.github/workflows/validate.yml) and
[`security-scan.yml`](../.github/workflows/security-scan.yml) run static,
lint, and source-configuration checks. Workflow definitions do not prove
external branch protection or required status checks. Workflow permissions,
OIDC configuration, deployment environment rules, and observed runtime access
must be reviewed independently before describing them as enforced.

## Backup, Recovery, and Disaster Readiness

The normal backend configuration requests S3 encryption with a customer-
managed KMS key. The bootstrap stack passes access-logging, deletion-protection,
and noncurrent-version retention inputs to an external module. The migration
helper checks that bucket versioning reports enabled before migration. These
are configuration and preflight facts; this repository does not provide
runtime evidence that the backend is deployed with the intended settings.

The migration helper creates local pre-migration copies for migration
recovery. Those copies are not a backend backup service, replication strategy,
or documented restore procedure. This repository does not define a complete
state restore/runbook, verified retention or recovery-point objective, or
disaster-recovery guarantee. Confirm the organization's approved backend
backup and incident-response procedures with the responsible owner. If state
integrity is uncertain, stop operations against it and escalate; do not delete,
edit, overwrite, or restore state using an undocumented command.

## Security and Data Handling

State, local backups, rendered configuration, plan output, and generated
Terraform files may contain sensitive values. Treat them as restricted
operational data:

- Never commit state, state backups, generated plans, credentials, or tokens.
- Never paste state contents or sensitive plan output into issues, chat,
  documentation, or unapproved logs.
- Use approved least-privilege execution identities and protect migration
  backups and artifacts under organizational controls.
- Do not expose backend identifiers, state keys, account identifiers, ARNs,
  or secret configuration in public documentation or routine reports.
- Do not bypass IAM, SCP, encryption, locking, review, or workflow controls;
  do not run concurrent operations against the same state.

These are safety requirements, not proof that external IAM, AWS bucket policy,
KMS key policy, SCP attachments, audit logging, or GitHub environment settings
are deployed or effective. Source policy files likewise do not prove
attachment or runtime enforcement. See [`SECURITY.md`](../SECURITY.md) and
the [security baseline checklist](../tests/smoke/security-baseline-checklist.md).

## Failure Handling and Troubleshooting

| Symptom | Possible cause | Safe next action and evidence |
| --- | --- | --- |
| Backend initialization fails | Missing/unresolved backend catalog values, wrong target context, or unavailable backend access | Stop; review approved configuration and sanitized error context. Do not add guessed values or switch backend ad hoc. |
| Lock contention | Another Terraform/Terragrunt operation may hold the state lock | Identify the stack and active workflow/operator activity; preserve lock/error metadata and escalate if ownership is unclear. Do not force-unlock without an authorized recovery procedure. |
| Access denied or identity mismatch | Credentials, trust, permissions, account, or Region may not match the intended operation | Stop and verify approved identity and target. Record workflow/run or sanitized local error; do not retry with broader credentials. |
| Migration reports backup, migration, or verification failure | Local copy, init migration, state pull, or backend metadata verification failed | Retain all state and backups, stop affected operations, preserve sanitized logs, and obtain stack-owner review before retry/recovery. |
| Plan or drift scan reports operational error | Provider, inventory, backend/state access, or execution failure | Distinguish operational error from detected drift; preserve stack and run evidence, then resolve access/configuration through review. Do not apply while state is uncertain. |
| Drift scan reports drift | Detailed plan exit code indicates changes are needed | Review the exact stack and plan through the approved change process. Drift output alone does not authorize a change. |

Use the owner metadata in [`inventory/stack-owners.yaml`](../inventory/stack-owners.yaml)
where a stack owner is defined. Follow the repository's
[contribution and review guidance](../CONTRIBUTING.md) and
[security policy](../SECURITY.md); this document does not define response-time
commitments or a separate incident escalation chain.

## Change Management

Changes to backend configuration, state-key derivation, migration scripts,
workflow identity or concurrency, and state-related tasks should be submitted
as reviewed repository changes with the affected operational documentation
updated. [`CODEOWNERS`](../CODEOWNERS), the
[pull request template](../.github/PULL_REQUEST_TEMPLATE.md), and
[`CONTRIBUTING.md`](../CONTRIBUTING.md) define repository review guidance.
Inspect the exact workflow run and plan evidence for the reviewed revision.
GitHub branch protection and environment approvals are enabled. Required
reviews are not currently enabled because the repository is maintained by a
single contributor. Required reviews should be enabled if additional
contributors or reviewers are added.

State migration and backend changes require a separately scoped, authorized
maintenance procedure.

## Related Documentation and Source Files

- [Repository overview and execution policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/README.md)
- [Security policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/SECURITY.md)
- [Contribution guidance](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/CONTRIBUTING.md) and [code owners](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/CODEOWNERS)
- [Bootstrap guide](bootstrap.md)
- [Deployment order](deployment-order.md)
- [Live infrastructure guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/README.md) and [workload guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/workloads/README.md)
- [Shared remote-state configuration](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/_envcommon/remote-state.hcl)
- [Root and shared Terragrunt configuration](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/terragrunt.hcl), [`common.hcl`](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/common.hcl), and [bootstrap stack](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/bootstrap/backend-bootstrap/terragrunt.hcl)
- [Backend creation helper](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/bootstrap/01-create-backend.py) and [migration helper](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/bootstrap/02-migrate-to-remote.py)
- [Task definitions](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Taskfile.yml) and [tool version pins](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tooling/.tool-versions)
- [Plan, drift, and post-apply scripts](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/ci/plan.py), [`drift-ci.py`](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/ci/drift-ci.py), and [`verify-post-apply.py`](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/ci/verify-post-apply.py)
- [Plan](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/plan.yml), [apply](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/apply.yml), [drift](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/drift-detection.yml),
[post-apply](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/post-apply-verify.yml), and [validation](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/validate.yml) workflows
- [Tests and verification guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/README.md) and [security baseline checklist](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/smoke/security-baseline-checklist.md)
