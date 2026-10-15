# Operations

## Purpose

This guide is for operators and contributors reviewing repository-managed infrastructure. It describes checked-in configuration and automation; it is not evidence that infrastructure has been deployed, is healthy, or is production-ready. Account, backend, and identity inputs still include placeholders.

Keep these operation classes distinct:

| Class | Typical effect |
| --- | --- |
| Read-only inspection | Reads repository files or local tool metadata. |
| Local setup or formatting | Local setup downloads and installs tools; formatting edits local files; both can write local caches. Neither contacts AWS unless the command explicitly does so. |
| Validation | Checks source/configuration. Some Terragrunt validation uses backend-disabled initialization; it can download modules/providers and write local caches. |
| Planning or state-aware review | Can authenticate to AWS, read remote state and cloud APIs, and acquire/release backend locks. Plans are sensitive and advisory. |
| Infrastructure or state mutation | Changes cloud resources or state location/content. Requires a separately authorized procedure. |
| CI-only automation | Runs under workflow conditions and credentials; a local task with a similar name is not equivalent. |

The task definitions in [Taskfile.yml](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Taskfile.yml) are the command source of truth. [justfile](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/justfile) and [Makefile](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Makefile) delegate to Task and do not define independent behavior.

## Operational Model

The live tree composes account and Region context with leaf Terragrunt stacks. The root [live/terragrunt.hcl](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/terragrunt.hcl) and [live/common.hcl](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/common.hcl) expose catalog data;
account and region files project that context. Shared layers configure providers, remote state, and tags. Module references are selected in [module-versions.hcl](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/catalogs/module-versions.hcl).

The bootstrap stack is exceptional: it starts with local state because the remote backend does not yet exist. Normal stacks include [remote-state.hcl](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/_envcommon/remote-state.hcl), which describes S3 state,
encryption, and DynamoDB locking. The checked-in backend metadata remains incomplete. Do not infer a usable backend from the presence of the configuration.

## Safety and Control Boundaries

The following distinctions are important when reviewing checks and operations:

- **Local and read-only:** `task verify-env` checks repository metadata and installed tools. It does not repair the host or establish AWS identity.
- **Local workspace effects:** formatting without `CHECK=true` edits HCL; setup scripts can install software; Terraform/Terragrunt init or validation may download dependencies and create local caches. Inspect task flags before running.
- **Backend-disabled validation:** `task validate:terraform` initializes with `-backend=false` and validates. It is not a cloud plan and is not proof of AWS identity or remote-state readiness.
- **State-aware planning:** a plan can read remote state and cloud APIs and can use backend locking. It is not infrastructure mutation, but it requires approved credentials and target verification and may expose sensitive data.
- **Mutation:** apply and bootstrap resource creation change infrastructure; migration changes state placement. Neither is a routine local check.
- **CI boundaries:** The workflows currently focus on validation and plan review; applying changes and provisioning AWS resources are intentionally disabled at this stage. As the project moves to a live deployment, the CI/CD workflows will be extended to apply reviewed changes and provision real infrastructure.

Local `apply` is prohibited. Infrastructure changes are applied exclusively through the CI/CD pipeline.

Never commit credentials, generated state, plan files, backend files, or provider caches. Treat plans, logs, state, and provider configuration as potentially sensitive. Do not manually edit remote state, bypass locking or policy controls, or use destructive operations to test readiness.

## Repository Execution Order

The authoritative sequence and readiness metadata are in [inventory/deployment-order.yaml](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/deployment-order.yaml).
The owner mapping is [inventory/stack-owners.yaml](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/stack-owners.yaml); [CODEOWNERS](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/CODEOWNERS) also provides repository review routing. Do not infer order from directory names or lexical path order.

| Phase | Inventory stacks | Key boundary |
| --- | --- | --- |
| Bootstrap | `backend-bootstrap` | First uses local state. Backend creation is followed by a separate local-to-remote state migration gate. |
| Management and archive prerequisites | `management-github-oidc`, `log-archive-kms` | Inventory marks this wave parallel; readiness and approval gates still apply. |
| Governance and archive storage | `management-scp`, `log-archive-bucket` | Inventory wave is marked parallel. The bucket has an explicit Terragrunt dependency on the KMS output. |
| Security services | `security-cloudtrail`, `security-guardduty` | CloudTrail has an explicit Terragrunt dependency on the archive bucket. GuardDuty delegated-administrator setup is separately identified as an operational prerequisite. |
| Workload baselines | `sandbox-scp-attachments`, `sandbox-security-baseline`, `sandbox-test-iam-roles` | Inventory marks one wave; its prerequisites remain distinct and must be checked per stack. |

Inventory phases, waves, readiness, approval flags, and `depends_on` entries
describe the intended order and are checked as inventory metadata by the
planning-matrix validator. They are not an apply orchestrator. Only the
log-archive-bucket to KMS and CloudTrail to bucket output edges are declared
as Terragrunt dependencies in the corresponding leaves. Other edges are
inventory-defined operational prerequisites, not automatically enforced by
Terragrunt. A wave marked parallel is not proof that simultaneous applies are
safe.

For the account, Region, exact stack path, current inputs, and dependency requirements, inspect that stack's leaf configuration and inherited account/region files. Confirm the owner from the owner inventory and route changes through repository review. Resolve placeholders only through approved changes; never guess account IDs, role values, or backend metadata.

## Safe Operator Workflow

| Step | Purpose and source | Effect classification | Evidence and failure response |
| --- | --- | --- | --- |
| 1. Confirm revision and root | Inspect Git status/revision and confirm the current directory is the repository root. Follow [CONTRIBUTING.md](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/CONTRIBUTING.md). | Read-only inspection. | Record revision and working tree state. Resolve unexpected local changes before interpreting checks. |
| 2. Identify shell/platform | Check the actual shell and platform before using a wrapper. Setup wrappers are [setup.sh](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/cross-platform/setup.sh) and [setup.ps1](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/cross-platform/setup.ps1); both delegate to [setup.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/cross-platform/setup.py). | Inspection is read-only; setup can install software and change the local host. | Capture platform, shell, and wrapper error. Do not run a provisioning setup path if local software installation is not approved. |
| 3. Check toolchain | Review pins in [tooling](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tooling/.tool-versions) and run `task verify-env` as described by the task and verifier. | Read-only local check. | Retain sanitized output and tool versions. Resolve missing or unsupported tools using the repository setup guidance. |
| 4. Confirm scope and ownership | Read both inventories, account/Region context, leaf HCL, shared includes, and module version. | Read-only inspection. | Record stack ID/path, owner, account alias, Region, dependencies, and revision. Stop if they disagree or contain unresolved placeholders. |
| 5. Run static validation | Use the named validation tasks below and inspect their exact Taskfile commands. | Validation; may write local caches/download dependencies. No AWS access is intended by backend-disabled Terraform validation. | Record command, revision, and result. Fix the source or escalate; do not bypass failed checks. |
| 6. Consider a plan only in an authorized context | The workflow Plan job runs cloud plans only for trusted `main`; see [plan.yml](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/plan.yml) and [plan.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/ci/plan.py). | State-aware read-only review: AWS identity, remote state, cloud reads, and possibly lock operations. | Review exact account, Region, state key, dependency outputs, replacements, and policy effects. Treat failures as unresolved, not as approval. |
| 7. Stop before mutation | Check governance and the current supported delivery path. | No mutation in this guide's normal workflow. | Escalate through the accountable owner and approved change process. Do not treat an advisory plan or safe-skip as authorization. |
| 8. Verify only through the supported check | The post-apply workflow/script checks an inventory selection and local rendered baseline; its live checks are pending. | CI-only check; local baseline portion renders config, no live AWS posture proof. | Preserve workflow summary and separately approved runtime evidence. A passing configuration check is not proof of deployment health. |

## Validation and Smoke Testing

Commands below are defined by [Taskfile.yml](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Taskfile.yml). Run from the repository root unless the task explicitly takes a target. These checks are not all equivalent:

| Command/workflow | Classification | What it checks and limits |
| --- | --- | --- |
| `task verify-env` | Read-only inspection | Repository metadata and installed tool pins; no AWS identity check. |
| `task fmt` | Formatting check only when `CHECK=true`; otherwise local file modification | Runs Terraform and Terragrunt formatters. Use check mode when only reviewing. |
| `task validate:terragrunt:hcl` | Local formatting validation | Terragrunt HCL format check; no cloud posture evidence. |
| `task validate:scp:json` | Local validation | Parses JSON policy files under `policies/scp`. |
| `task lint:yaml`, `task lint:markdown`, `task lint:terraform`, `task lint:actions` | Local lint | Run configured linters. `lint:terraform` and Actionlint require their tools. |
| `task validate:terraform` | Backend-disabled local validation | Runs init with `-backend=false`, then validate. May retrieve modules/providers and write local caches; it does not validate remote state or AWS resources. |
| `task verify:security-baseline` | Local rendered-configuration smoke check | [verify-security-baseline.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/smoke/verify-security-baseline.py) checks configured baseline through local Terragrunt renders. It is not a live AWS security assessment. |
| `task plan` | State-aware planning | Calls [plan.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/ci/plan.py). The default task is non-strict and known placeholder/credential failures may be tolerated. It can access remote state/cloud APIs and is not a deployment approval. Avoid local cloud planning unless the documented prerequisites and authorization are satisfied. |
| Plan workflow pull-request job | CI-only metadata validation | Checks changed-stack selection and inventory without AWS access; it does not create a cloud plan. |
| Plan workflow trusted-main job | CI-only state-aware planning | Assumes a configured read-only identity and plans remote-state stacks. A green result is only meaningful within the script's reported scope; output is advisory and is not saved for apply. |
| Drift review | State-aware, read-only drift inspection | `task drift` uses [drift-ci.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/ci/drift-ci.py) to inspect remote-state stacks and requires cloud/backend access. The CI workflow invokes the same `task drift` command, typically through a scheduled or manual execution using a read-only identity. The process is review-only and does not repair or apply drift. |
| Post-Apply Verification workflow | CI-only configuration check | Manually selects an inventory stack and commit. [verify-post-apply.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/ci/verify-post-apply.py) runs configured checks and reports live checks pending; it does not prove deployment or live health. |
| Apply workflow | CI-only safe skip | Until this project transitions to live infrastructure, the CI workflow intentionally runs `task apply` with `APPLY=false`; therefore, no AWS resources are created or modified. |

The complete `task validate` aggregate also runs repository lint tasks; inspect its dependencies and installed tool requirements before use. The security workflow runs configured scanners through `task security-all`; its scope, exclusions, and thresholds are defined in the Taskfile and workflow. Passing a scanner is evidence only for that configured scan.

The local `task init` target uses backend-disabled initialization, but initialization can download dependencies and change local caches. Do not confuse it with state migration. The bootstrap helper's dry-run/list/plan modes are preparatory only; actual backend creation and migration modes are infrastructure/state mutations and are outside ordinary validation.

## Planning vs Mutation

Planning is not mutation, but it is state-aware: it may contact AWS, read remote state, call provider APIs, and interact with backend locking. Require an approved identity, verified target context, ready backend and dependencies, and an authorized reason before a cloud plan. Do not print or publish raw state or plan contents.

The Plan workflow's pull-request path is metadata-only. Its trusted-main path
creates read-only advisory plans, but the workflow states that plans have no
saved-plan consumer and do not authorize apply. The checked-in Apply workflow
intentionally sets `APPLY=false`; it provides no AWS credentials and is a safe
skip. Although Taskfile exposes an `apply` task with an enabling path, that
path is infrastructure-mutating and is not a supported routine deployment
workflow. Do not enable it as a substitute for the missing approved saved-plan
deployment path.

The bootstrap stack's first apply creates backend resources with local state;
the separate migration procedure changes state placement. In
[01-create-backend.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/bootstrap/01-create-backend.py),
`--dry-run` validates and reports intended commands without running Terraform,
while `--plan` runs backend-disabled init, validation, and a Terraform plan.
That plan is non-mutating but may make provider/API reads and needs appropriate
context. In [02-migrate-to-remote.py](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/bootstrap/02-migrate-to-remote.py),
list/plan/dry-run modes inspect stack selection and local metadata;
`--migrate` validates AWS/backend context, creates backups, and changes state
placement. Creation and migration are controlled operations with their own
approval and recovery requirements. Do not use creation, migration, import,
destroy, state editing, or recovery commands to test an environment.

## Troubleshooting

| Symptom | Likely cause | Safe diagnostic and evidence | Next step |
| --- | --- | --- | --- |
| Runtime or tool missing/version mismatch | Host does not meet a pin or verifier requirement. | Read tool pin files and run `task verify-env`; retain sanitized version/error output. | Use documented setup flow or Dev Container; raise a tooling issue if pins conflict. |
| Setup fails on shell/platform | Wrong shell, wrapper unavailable, or host platform not recognized. | Record shell, OS, wrapper path, and error; inspect [cross-platform guidance](cross-platform.md). | Use the matching checked-in wrapper; do not improvise another installer. |
| Path, quoting, or command-not-found error | Wrong working directory, missing tool, or shell-specific syntax. | Confirm repository root and exact task name in Taskfile; capture command and exit code. | Retry only with the supported shell/task interface; correct documentation drift through review. |
| Line ending or executable-bit problem | File attributes or wrapper invocation mismatch. | Inspect file attributes and use the documented PowerShell or Bash invocation; do not edit unrelated files. | Follow [cross-platform.md](cross-platform.md) and report the affected path. |
| AWS identity/credential failure | Missing/expired identity, incorrect role context, or incomplete configuration. | In an approved environment, verify caller identity and intended account/Region without exposing identifiers or credentials in logs. Capture sanitized role/session and failing operation. | Stop cloud operations and contact the accountable identity/stack owner. Never fall back to ambient credentials silently. |
| Backend/state/lock error | Backend values unresolved, inaccessible state, concurrent operation, or provider/backend mismatch. | Capture stack ID, revision, sanitized error and lock context; check workflow concurrency and approved backend readiness. Do not expose bucket/key identifiers. | Stop and escalate to state/backend owner. Never edit state or bypass locking; recovery is a separately approved procedure. |
| Validation mismatch or unexpected plan | Catalog/include/module change, missing dependency output, stale state, or material replacement/policy change. | Capture stack, source revision, check name, sanitized diff/summary, and dependency/readiness evidence. | Stop downstream work; request owner review and correct configuration/inventory through a reviewed change. |
| CI-only failure | Workflow condition, pinned tool setup, missing repository configuration, or actual script/task mismatch. | Capture workflow name, run URL/reference, commit, failed step, and sanitized logs. Verify actual task/script definitions. | Escalate to workflow/stack owner. Specifically, verify the drift workflow task mismatch before treating its run as a drift result. |
| Ownership/order ambiguity | Missing or inconsistent inventory owner, phase, wave, or dependency. | Compare both inventories, CODEOWNERS, and leaf Terragrunt dependencies; record conflicting entries. | Stop and route a reviewed inventory/documentation correction before proceeding. |

## Security and Governance

Repository-defined guardrails include reviewed contribution/change processes,
deployment-order and owner inventories, policy documents under [policies/scp](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/policies/scp/), and the security requirements in [SECURITY.md](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/SECURITY.md).
SCP policy files and stack configuration document the intended governance controls and provide a clear foundation for their controlled rollout and future validation in the live environment.

Operational recommendations: use least-privilege, approved identities; verify
intended account, Region, stack, and state before any cloud operation; preserve
workflow and review evidence; do not bypass approval, IAM/SCP boundaries,
backend locking, or validation; never manually edit remote state; do not run
destructive commands to test readiness.

## Related Documentation

- [Repository overview and operating policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/README.md)
- [Security policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/SECURITY.md)
- [Contribution guidance](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/CONTRIBUTING.md)
- [Bootstrap overview](bootstrap.md)
- [Deployment order and dependencies](deployment-order.md)
- [State management](state-management.md)
- [Cross-platform setup](cross-platform.md)
- [Live configuration guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/README.md)
- [Workload configuration guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/workloads/README.md)
- [Test and smoke-check guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/README.md)
- [Stack deployment inventory](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/deployment-order.yaml)
- [Stack ownership inventory](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/stack-owners.yaml)
- [Task definitions](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Taskfile.yml)
- [Convenience task wrappers](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/justfile), [Makefile](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Makefile)
- [Validation workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/validate.yml)
- [Plan workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/plan.yml)
- [Apply safe-skip workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/apply.yml)
- [Drift workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/drift-detection.yml)
- [Post-apply verification workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/post-apply-verify.yml)
- [Security scan workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/security-scan.yml)

## Maintenance Notes

Update this guide in the same reviewed change as operational changes to task behavior, workflows, inventories, state configuration, account/Region composition, or smoke checks. Recheck each linked path and command against the checked-in source. Describe workflow success only with run evidence and scope; do not turn declared intent into a claim of deployed or enforced infrastructure.
