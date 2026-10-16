# Platform Live Infrastructure

[![Validate](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/validate.yml)
[![Security Scan](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/security-scan.yml/badge.svg?branch=main)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/security-scan.yml)
[![Cross-Platform Tests](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/cross-platform-test.yml/badge.svg?branch=main)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/cross-platform-test.yml)
[![GitHub Release](https://img.shields.io/github/v/release/Mahdiar-Farzinfar/platform-live-infra?display_name=tag&sort=semver)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/releases/latest)
[![Dev Container](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/devcontainer-image.yml/badge.svg?branch=main)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/devcontainer-image.yml)
[![Drift Detection](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/drift-detection.yml/badge.svg?branch=main)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/drift-detection.yml)
[![Post-Apply Verification](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/post-apply-verify.yml/badge.svg?branch=main)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/post-apply-verify.yml)
[![Terraform Plan](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/plan.yml/badge.svg?branch=main)](https://github.com/Mahdiar-Farzinfar/platform-live-infra/actions/workflows/plan.yml)
[![Security Policy](https://img.shields.io/badge/security-policy-blue)](./SECURITY.md)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Code of Conduct](https://img.shields.io/badge/code%20of%20conduct-adopted-blue)](./CODE_OF_CONDUCT.md)
[![Renovate](https://img.shields.io/badge/Renovate-enabled-1A1F6C?logo=renovatebot&logoColor=white)](./.github/renovate.json)
[![Documentation](https://img.shields.io/badge/documentation-MkDocs-526CFE?logo=materialformkdocs&logoColor=white)](https://Mahdiar-Farzinfar.github.io/platform-live-infra/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Mahdiar-Farzinfar/platform-live-infra/badge)](https://scorecard.dev/viewer/?uri=github.com/Mahdiar-Farzinfar/platform-live-infra)

`platform-live-infra` is the live-environment orchestration repository for a
multi-account AWS platform. It uses Terragrunt to compose released Terraform
modules, select accounts and Regions, configure providers and remote state,
and enforce an explicit deployment sequence.

The reusable Terraform implementations live in the companion
[`platform-iac-modules`](https://github.com/Mahdiar-Farzinfar/platform-iac-modules)
repository. This repository owns the environment composition and operational
decisions; it does not duplicate module resource logic.

> **Current status:** account identifiers, backend metadata, organization
> targets, and some identity values are still explicit `TBD` placeholders.
> These `TBD` and placeholder values will be replaced with approved real
> values at the appropriate time, and this project will eventually evolve into
> a real, production-ready live platform. Populate and review those values
> before any apply. Until then, this project does not claim to be production
> ready, and no production deployment is claimed by this document.

## Responsibilities

This repository owns:

- account, Region, and environment composition;
- Terragrunt inheritance, provider configuration, and state isolation;
- released module selection through `live/catalogs/module-versions.hcl`;
- AWS Organizations policies and their target decisions;
- deployment phases, stack dependencies, ownership metadata, and readiness gates;
- bootstrap and state-migration procedures;
- plan, apply, drift, and post-deployment operational practices.

`platform-iac-modules` owns reusable Terraform resource implementations,
variable validation, module tests, and module releases. A live stack should
consume a versioned module source rather than copy module internals or use a
moving branch.

## Architecture

```text
platform-live-infra/
├── live/
│   ├── bootstrap/backend-bootstrap/       # one-time encrypted state backend
│   ├── foundation/
│   │   ├── management/                     # management identity and SCPs
│   │   ├── log-archive/                    # KMS and immutable audit storage
│   │   └── security/                       # CloudTrail and GuardDuty services
│   ├── workloads/sandbox-account/          # workload account composition
│   ├── _envcommon/                         # provider, backend, and tag layers
│   ├── catalogs/                           # account, Region, tag, module data
│   ├── common.hcl                          # shared catalog projections
│   └── terragrunt.hcl                      # root shared locals
├── inventory/
│   ├── deployment-order.yaml               # phases, waves, and dependencies
│   └── stack-owners.yaml                   # deployable-stack ownership
├── policies/scp/                           # AWS Organizations SCP documents
├── scripts/bootstrap/                      # backend and state migration tools
├── scripts/tools/                          # environment/tooling utilities
├── docs/                                   # architecture and implementation notes
├── tooling/                                # pinned versions and scanner config
├── .devcontainer/                          # reproducible development setup
├── SECURITY.md
└── LICENSE
```

### Scope hierarchy

Normal deployable leaves follow this hierarchy:

```text
scope → account → Region → stack
```

`account.hcl` contains account metadata, `region.hcl` projects the approved
Region and account context, and leaf `terragrunt.hcl` files select modules and
inputs. Shared `_envcommon` layers generate the AWS provider, S3 remote state,
and standard tags. The root and common files expose catalog projections without
creating resources.

The current live tree contains ten deployable leaves:

- `live/bootstrap/backend-bootstrap`
- `live/foundation/management/us-east-1/github-oidc`
- `live/foundation/management/us-east-1/scp`
- `live/foundation/log-archive/us-east-1/kms`
- `live/foundation/log-archive/us-east-1/log-archive-bucket`
- `live/foundation/security/us-east-1/cloudtrail`
- `live/foundation/security/us-east-1/guardduty`
- `live/workloads/sandbox-account/us-east-1/scp-attachments`
- `live/workloads/sandbox-account/us-east-1/security-baseline`
- `live/workloads/sandbox-account/us-east-1/test-iam-roles`

## Deployment order

The authoritative DAG is [`inventory/deployment-order.yaml`](inventory/deployment-order.yaml).
It defines phases, parallelizable waves, explicit `depends_on` relationships,
readiness requirements, approval gates, and post-deployment checks.

The normal sequence is:

1. Bootstrap the encrypted S3/DynamoDB state backend using local state.
2. Review backend outputs and migrate consuming stacks to remote state.
3. Prepare management identity and the Log Archive KMS key.
4. Apply management governance and create the Log Archive bucket.
5. Deploy the Security-account CloudTrail and GuardDuty foundations.
6. Deploy workload SCP attachments, GuardDuty baseline, and test IAM identity.

Some stacks in the same wave may run in parallel, but only after their
dependencies and readiness checks are satisfied. Organization-wide SCPs,
encryption keys, audit logging, and identity changes require explicit review.

## Prerequisites

Before deployment, confirm:

- AWS accounts and Organizations resources exist and their IDs are populated in
  `live/catalogs/accounts.hcl`;
- approved Regions are represented in `live/catalogs/regions.hcl`;
- backend bootstrap metadata and KMS inputs are available to
  `live/common.hcl`;
- the deployment identity is authorized for the target account and operation;
- GitHub OIDC subjects, role permissions, SCP targets, retention, and break-glass
  procedures have been reviewed;
- the selected module refs in `live/catalogs/module-versions.hcl` are approved;
- the required Terraform and Terragrunt versions are installed.

The catalogs currently contain placeholders such as `TBD`. Do not replace them
with guessed identifiers. A bootstrap or apply must fail closed until approved
values are supplied.

## Toolchain and setup

Pinned versions are recorded in:

- `tooling/.terraform-version`;
- `tooling/.terragrunt-version`;
- `tooling/.tool-versions`.

The repository supports Windows, Linux, and macOS helper scripts. The
`.devcontainer/` directory provides a reproducible development environment.
The checked-in tool installer and verifier are:

```text
scripts/tools/install-tools-posix.go
scripts/tools/install-tools-windows.go
scripts/tools/verify-env.py
```

### Setup

Install the pinned toolchain using the repository’s native setup scripts, then verify the installation before running Terraform or Terragrunt.

- On **Linux** or **macOS**, run:

  ```bash
  ./scripts/cross-platform/setup.sh
  ```

- On **Windows**, run:

  ```powershell
  .\scripts\cross-platform\setup.ps1
  ```

These scripts under `./scripts/cross-platform/` are the single source of truth (SoT) for setup behavior. Any higher-level task runner or wrapper should delegate to them.

> Do not commit provider caches, state files, plans, or generated files.

To discover the available commands in the Taskfile, Makefile, and justfile,
run the corresponding command from the repository root:

```bash
task --list
just --list
make help
```

## Infrastructure execution policy

GitHub Actions is the required execution path for routine infrastructure
changes to all environments managed by this repository, including sandbox
environments. Local tooling is not an alternative routine deployment path.

Manually triggering an approved GitHub Actions workflow is permitted and
remains a workflow-based operation. This is distinct from running deployment
commands directly from a workstation.

### Permitted local operations

Local formatting, linting, validation, and tests that do not create, modify,
or delete infrastructure are permitted and encouraged. Integration tests
that change infrastructure remain subject to the deployment policy.

Local plans are permitted for development and troubleshooting when using an
authorized identity, the intended account, Region, and backend, and the
minimum permissions required for planning, dependency-output access, and
state locking.

Initialization and planning must not provision backend resources, migrate
state, or invoke infrastructure-changing hooks. Any such operation requires
a separately approved procedure.

Local plans are advisory. They do not replace the deployment workflow's plan
or authorize an apply. Plan output and saved plan files may contain sensitive
information and must be handled accordingly.

### Routine infrastructure changes

Routine applies must execute through the approved deployment workflow.
Direct execution of `terraform apply`, `terragrunt apply`, or `task apply`
outside that workflow is not an approved routine deployment method.

The required deployment process is to:

- identify the exact stack, account, Region, backend, and source revision;
- validate approved inputs, dependencies, and readiness requirements;
- generate a saved plan in a trusted workflow execution context;
- obtain the approvals required for the target environment and change;
- apply that exact approved saved plan;
- prevent conflicting operations against the same state;
- preserve appropriate execution records and perform post-apply verification.

The saved plan must be associated with its source revision, target, and
workflow run, protected against unauthorized replacement or disclosure, and
retained only as long as operationally necessary.

If the plan is stale, invalid, or must be regenerated, stop the deployment.
Generate and review a replacement plan and obtain the required approvals
again. Approval of an earlier plan does not authorize a different plan or
source revision.

Destroy operations and state-changing maintenance are not implicit extensions
of an apply approval. They require an explicitly scoped, approved procedure.

### Controlled exceptions

Execution outside the normal deployment workflow is permitted only for
explicitly authorized operations such as:

- initial backend or deployment-identity bootstrap, before the normal
  workflow can operate;
- state migration or state repair under an approved maintenance procedure;
- emergency recovery when the normal deployment path is unavailable or
  cannot safely perform the required recovery.

Before execution, record the reason, responsible operator, authorization,
target scope, and recovery approach. Confirm the account, Region, backend,
and state ownership; prevent concurrent deployment activity; and use a
scoped, short-lived identity. Emergency human access must use the approved
break-glass authentication controls.

Preserve relevant execution logs and recovery artifacts securely. After the
operation, reconcile any required configuration changes in Git, verify state
and infrastructure, end temporary access, and complete the required change
or incident review before resuming routine deployments.

Workflow inconvenience or a failed approval gate does not justify an
exception. Local execution must not bypass unresolved placeholders, missing
dependencies, or required approvals.

### Policy and enforcement status

This section defines the required operating policy; documentation alone does
not enforce it.

Technical enforcement requires reviewed IAM permissions and OIDC trust,
protected branches and deployment environments, required reviews and
approval gates, restricted plan artifacts, and concurrency and state-locking
safeguards.

Routine human identities must not provide an alternative infrastructure-write
or Terraform-state-write path. Planning identities may receive the narrowly
scoped permissions required to acquire and release state locks; these must
not grant permission to modify Terraform state snapshots.

Changes to workflows and deployment-affecting scripts must receive appropriate
review. Untrusted pull-request code must not receive deployment credentials
or access to sensitive state and plan artifacts.

Until these controls and the exception procedures have been implemented and
verified, this repository does not claim that workflow-only deployment is
technically enforced. Routine deployments must not proceed through any
execution path that does not meet the requirements of this policy.

## Bootstrap and remote state

The backend bootstrap stack is intentionally different from normal stacks:
it does not include `live/_envcommon/remote-state.hcl`, because the backend
does not exist on its first apply.

Initial backend and deployment-identity bootstrap may require a controlled
exception to the normal workflow-only deployment policy. This exception is
limited to the resources needed to establish the approved deployment path;
it does not authorize direct deployment of unrelated stacks.

The preparation commands below do not authorize a state-changing operation.
Before creating the backend or migrating state outside an approved workflow,
follow the controlled-exception requirements in
[Infrastructure execution policy](#infrastructure-execution-policy),
including recorded authorization, target verification, scoped credentials,
and appropriate recovery safeguards.

Once the backend and deployment identity are operational, routine changes
must use the approved deployment workflow. Subsequent backend maintenance
and state migration require a separately approved procedure.

For bootstrap, use the following commands:

```bash
task bootstrap:create-backend -- --dry-run
task bootstrap:create-backend -- --plan
```

The bootstrap command validates the required repository inputs and
orchestrates the Terragrunt commands.

After the backend is created and its outputs are reviewed, inspect and
prepare the migration of consuming stacks to remote state with the following
commands:

```bash
task bootstrap:migrate-to-remote -- --list-stacks
task bootstrap:migrate-to-remote -- --plan
task bootstrap:migrate-to-remote -- --dry-run
```

Actual migration is a state-changing operation. Use
`task bootstrap:migrate-to-remote -- --migrate` only after reviewing backups,
backend configuration, and the selected stack set. The tool supports stack
selection, include/exclude filters, backups, confirmation, and fail-fast or
keep-going behavior. Never delete recovery backups as part of an unrelated
change.

Normal stacks inherit the S3 backend from `_envcommon/remote-state.hcl`. The
state key is derived from the stack hierarchy, and the backend requires
encryption and a customer-managed KMS key. Backend metadata is intentionally
not guessed from ambient credentials or environment variables.

## Planning and applying stacks

Stack operations follow the
[Infrastructure execution policy](#infrastructure-execution-policy):
local validation and advisory planning are permitted, while routine applies
must run through the approved GitHub Actions deployment workflow.

### Local validation and advisory planning

Use the repository `Taskfile` as the primary local interface for Terragrunt
stack operations. The repository-wide Terragrunt tasks
`fmt:terragrunt:hcl`, `validate:terragrunt:hcl`, `render:terragrunt`, and
`validate:terraform` operate across the full `live/` tree by default. To scope
one command to a single deployable stack, provide `TARGET` explicitly:

```bash
task fmt:terragrunt:hcl TARGET=live/foundation/security/us-east-1/guardduty
task validate:terragrunt:hcl TARGET=live/foundation/security/us-east-1/guardduty
task render:terragrunt TARGET=live/foundation/security/us-east-1/guardduty
task validate:terraform TARGET=live/foundation/security/us-east-1/guardduty
```

Stack-oriented operations such as `init`, `plan`, and `apply` continue to use
`live/foundation/security/us-east-1/guardduty` as their default target; set
`TARGET` explicitly when operating on another stack.

With an authorized planning identity and the intended account, Region, and
backend, initialize the stack, validate its configuration, and generate an
advisory plan:

```bash
task init-validate-plan TARGET=live/foundation/security/us-east-1/guardduty
```

This task sequence does not apply infrastructure changes. The individual
steps can also be run separately:

```bash
task init TARGET=live/foundation/security/us-east-1/guardduty
task validate:terraform TARGET=live/foundation/security/us-east-1/guardduty
task plan TARGET=live/foundation/security/us-east-1/guardduty
```

Before running these commands, confirm that initialization and planning will
not provision backend resources, migrate state, or invoke infrastructure-changing
hooks. Any such operation requires its own approved procedure.

Review the account, Region, provider identity, dependency outputs, policy
targets, and resource replacements in every plan. Use
`inventory/deployment-order.yaml` to select a safe order rather than applying
all directories lexically.

Local plan output is for development and troubleshooting. It is not the
deployment approval artifact and must not be substituted for the plan
generated by the approved deployment workflow.

### Workflow-based deployment

Submit infrastructure changes through the repository's reviewed change
process. Use the approved GitHub Actions plan and apply workflows for the
explicit target stack and source revision.

Before apply, the deployment process must verify:

- the target account, Region, backend, and deployment identity;
- approved catalog values and module versions;
- deployment-order dependencies and readiness requirements;
- the saved plan associated with the reviewed source revision;
- the required owner and environment approvals;
- protection against concurrent operations on the same state.

Apply must consume the exact approved saved plan. If the source revision,
target, or proposed actions change, or the plan can no longer be safely
applied, stop and repeat planning, review, and approval.

Manually starting an approved workflow is permitted. Running a local apply
instead of using that workflow is not.

Do not use `apply`, `destroy`, or state migration to bypass unresolved `TBD`
values, missing dependencies, or required approvals. Treat SCP target
changes, KMS deletion settings, Object Lock, CloudTrail destinations,
GuardDuty organization settings, and IAM/OIDC trust policies as high-impact
changes requiring explicit review.

### Direct-apply tooling

The repository exposes `task apply` as a low-level interface. Its availability
does not authorize routine execution outside the deployment workflow.

`task apply` currently runs `terragrunt apply`; it does not rerun the
`init-validate-plan` sequence or consume the saved plan from an earlier review.
It generates a new execution plan at apply time and therefore is not, by
itself, an implementation of the approved-saved-plan deployment process.

If an approved bootstrap or recovery procedure explicitly uses this command,
review the newly generated plan before confirming. If it differs from the
authorized change scope, cancel and obtain a new review and authorization.
Do not bypass the interactive confirmation with `-auto-approve` in that
direct-apply procedure.

All execution outside the normal deployment workflow remains subject to the
controlled-exception requirements in the infrastructure execution policy.

## Security controls

The live composition currently provides:

- management-account GitHub OIDC federation;
- AWS Organizations SCP documents under `policies/scp/`;
- centralized, multi-Region CloudTrail with global service events and log-file
  validation;
- Log Archive KMS encryption, private versioned storage, and Object Lock;
- Security-account GuardDuty organization configuration;
- sandbox-account GuardDuty protection features;
- exact-subject GitHub OIDC trust for the sandbox IAM validation role.

The SCP module is organization-context sensitive and must run with management
account credentials. The GuardDuty module separates management-account
delegated-administrator registration from delegated-security-account
organization configuration. CloudTrail delivery uses the Log Archive bucket,
whose policy and retention ownership remain in the Log Archive stack.

Do not introduce wildcard principals, unrestricted GitHub subjects,
administrator policies, public storage, or IAM users as a shortcut around
missing identity metadata. The security policy and operational expectations are
documented in [`SECURITY.md`](SECURITY.md).

## Naming, tags, and versions

Names should be deterministic, stable, lowercase where AWS naming rules require
it, and independent of unresolved account IDs when possible. Standard tags are
composed by `live/_envcommon/tagging.hcl` from `live/catalogs/tags.hcl`, account
metadata, environment metadata, and stack-specific component tags.

Module sources and release refs are resolved through
[`live/catalogs/module-versions.hcl`](live/catalogs/module-versions.hcl), which
projects versioned Git sources from `platform-iac-modules`. Update the catalog
through a reviewed change; do not hard-code a moving branch or silently change
module ownership.

## Code quality and security checks

Run the complete repository verification workflow before submitting changes for
review:

```bash
task ci
```

This command runs the repository's formatting, linting, and security checks.
For targeted verification, the relevant checks can also be run separately:

```bash
pre-commit run --all-files
task security-all
```

## Operations and troubleshooting

When a deployment fails:

1. Record the exact stack path, account, Region, command, and plan context.
2. Check backend connectivity, state locks, credentials, and provider account
   identity before changing infrastructure.
3. Inspect the nearest dependency in `inventory/deployment-order.yaml`.
4. For cross-account failures, verify the destination bucket/KMS policy and the
   intended service principal.
5. For Organizations failures, verify management/delegated-admin context and
   target IDs.
6. Preserve state backups and do not force-unlock or disable controls without
   an approved incident or recovery procedure.

Drift detection should use read-only plans with the same state, provider, and
account safeguards as normal changes. Post-deployment checks should confirm
identity, encryption, logging, policy scope, and security-service health.

### Failure recovery and rollback

Terraform does not automatically roll back changes when `apply` fails.
Some operations may already have succeeded; treat the affected stack as
potentially partially applied.

After completing the initial troubleshooting above:

1. Pause further deployments to the affected stack and its dependents.
   Confirm that no apply is still running before attempting recovery.
2. Determine which operations succeeded using the apply output, current
   state, and service-side checks. A failed run may leave resources that
   are not recorded in state, particularly if state persistence failed.
3. Resolve the underlying error and generate a fresh plan through the approved
   deployment workflow for the same explicit stack, using the intended
   account, Region, and backend. A plan proposes changes; it does not repair
   infrastructure.
4. If the current configuration remains the desired target, review the new
   plan, obtain the required approvals, and apply that exact saved plan
   through the approved workflow to complete or correct the deployment.
5. If the change must be reversed, prepare a corrective configuration change
   in Git, restoring previous settings or module versions only where safe.
   Generate, review, and approve a fresh workflow plan before applying it.
   `git revert` alone does not change infrastructure, and reverting
   configuration does not guarantee restoration of previous resources or
   their data.
6. Verify the resulting infrastructure and affected dependencies before
   resuming deployment. Confirm identity, encryption, logging, policy
   scope, and security-service health as applicable.

A failed deployment does not, by itself, authorize a local apply. Recovery
must use the normal deployment workflow whenever that path is available and
can safely perform the required operation.

If the workflow is unavailable or recovery requires an operation outside its
supported scope, stop and invoke the approved controlled-exception procedure
described in
[Infrastructure execution policy](#infrastructure-execution-policy).
Prevent concurrent deployments, preserve recovery evidence, and obtain the
required authorization before performing direct infrastructure or state
changes.

Any replacement plan requires a new review and the required approvals.
Neither the failed run's approval nor an earlier local plan authorizes
different recovery actions.

Do not use `destroy`, manual resource deletion, state edits, or state-entry
removal as a generic rollback mechanism. Use import or other state-repair
operations only after diagnosing a specific state/resource mismatch and
reviewing the recovery procedure. Force-unlock is appropriate only for a
confirmed stale lock, after verifying that no operation still owns it.

Restoring an older state snapshot does not restore infrastructure or data.
Reserve state restoration for diagnosed state-loss, corruption, or
migration-recovery scenarios under a reviewed recovery procedure. If Terraform
reports a state-write failure, preserve any recovery state file it produces
and resolve state persistence before another plan or apply.

Changes involving deleted or replaced resources, persistent data, or
irreversible retention controls may require service-specific recovery or
backup restoration. A corrective apply cannot recover lost data or bypass
Object Lock retention restrictions. Escalate service disruption, unexpected
destructive changes, or uncertain state integrity to the responsible owner
before proceeding.

## Change management

Keep changes small and scoped to one account, Region, stack, policy, or module
promotion where possible. A review should include:

- the exact stack and account/Region target;
- dependency and deployment-order impact;
- a reference to the trusted workflow run and the plan associated with the
  exact source revision and deployment target;
- a reviewable plan summary with sensitive values redacted; full plan
  artifacts must remain access-controlled and must not be posted publicly;
- policy, trust, KMS, retention, and destruction implications;
- updates to `inventory/deployment-order.yaml` or
  `inventory/stack-owners.yaml` when topology or ownership changes;
- rollback or recovery considerations.

For an authorized operation outside the normal deployment workflow, the
change or incident record must additionally identify:

- the reason the normal workflow cannot be used;
- the approving authority and responsible operator;
- the exact target scope and temporary access granted;
- the reviewed execution and recovery procedure;
- the operation outcome and any state or infrastructure discrepancies;
- post-operation verification, Git reconciliation, and temporary-access
  termination.

An exception authorizes only its recorded scope and duration. It does not
establish an alternative deployment path for subsequent changes.

Do not commit state files, plans, credentials, provider caches, or generated
Terragrunt artifacts. Use CODEOWNERS and the repository security policy for
review and reporting expectations.

## Documentation and support

The primary documentation for this platform is available in the
[Platform Live Infrastructure documentation](https://Mahdiar-Farzinfar.github.io/platform-live-infra/).
Additional architecture and implementation notes are kept under [`docs/`](docs/),
and the MkDocs configuration is [`mkdocs.yml`](mkdocs.yml).

If you are using this repository as a reference or planning a change, review the
documentation for the relevant area first so you understand the expected
structure, dependencies, and prerequisites. Keep any change scoped to the
smallest affected area, and make sure it aligns with the documented deployment
order and operational guidance.

For contributions, preserve least privilege, explicit ownership, deterministic
state identity, and cross-platform compatibility.

## License

This repository is licensed under the terms in [`LICENSE`](LICENSE).

For vulnerability or security-control concerns, follow
[`SECURITY.md`](SECURITY.md) rather than publishing sensitive details in a
public issue.
