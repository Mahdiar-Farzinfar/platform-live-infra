# Infrastructure Deployment Order

This guide records the deployment sequence and dependency evidence in the checked-out repository. It describes configuration and workflow behavior; it does not attest that any stack has been applied, is healthy, or is free of drift.

## Authority and evidence

[`inventory/deployment-order.yaml`](../inventory/deployment-order.yaml) is the declared deployment inventory. It lists ten Terragrunt leaves, phases, waves, `parallel` flags, readiness gates, post-deployment checks, and stack `depends_on` metadata. [`inventory/stack-owners.yaml`](../inventory/stack-owners.yaml) maps those leaf paths to owners.

The plan-matrix validator reads both inventories. It checks stack discovery, IDs, phase/wave assignment, ownership coverage, and that declared dependencies occur in an earlier phase or wave. This validates inventory metadata; it does not deploy stacks or schedule applies.

Terragrunt also declares two concrete output dependencies: the log archive bucket consumes the KMS stack output, and CloudTrail consumes the log archive bucket output. Other inventory dependencies are not represented by a Terragrunt `dependency` or `dependencies` block in the corresponding leaf. Treat those as inventory-defined operational prerequisites, not Terragrunt-enforced edges.

Evidence labels used below:

- **Terragrunt-enforced**: a leaf configuration declares a Terragrunt dependency.
- **Inventory-defined**: a prerequisite is listed in the deployment inventory and checked as metadata by the plan-matrix validator.
- **Workflow/script-enforced**: workflow or script behavior checks or orders the operation.
- **Documentation-defined**: an operational convention stated in repository documentation.
- **Operational prerequisite**: inventory readiness or service setup that must be confirmed at runtime; the repository does not automate that confirmation.

## Verified sequence

The inventory order is the operator sequence. Complete a phase's readiness checks before entering the next phase. Inventory `parallel: true` describes a declared wave boundary; it is not proof that concurrent applies are safe or an execution guarantee. Serialize applies unless the operators have separately confirmed independent states, credentials, service prerequisites, and change windows.

1. **Bootstrap**
   - Stack: [`live/bootstrap/backend-bootstrap`](../live/bootstrap/backend-bootstrap/terragrunt.hcl); sole stack in a `parallel: false` wave.
   - Gate: approve concrete inputs, create the backend with local state, verify it, and record the separate local-to-remote migration before remote-state operations.
2. **Management and archive prerequisites**
   - Stacks: [`live/foundation/management/us-east-1/github-oidc`](../live/foundation/management/us-east-1/github-oidc/terragrunt.hcl) and [`live/foundation/log-archive/us-east-1/kms`](../live/foundation/log-archive/us-east-1/kms/terragrunt.hcl); inventory wave marked `parallel: true`.
   - Gate: verify account/provider context, exact OIDC trust and role permissions, and approved KMS administration and service access.
3. **Governance and archive storage**
   - Stacks: [`live/foundation/management/us-east-1/scp`](../live/foundation/management/us-east-1/scp/terragrunt.hcl) and [`live/foundation/log-archive/us-east-1/log-archive-bucket`](../live/foundation/log-archive/us-east-1/log-archive-bucket/terragrunt.hcl); inventory wave marked `parallel: true`.
   - Dependency and gate: the bucket has a Terragrunt KMS dependency. Review SCP targets and exceptions; settle Object Lock/retention decisions and verify the key output and CloudTrail delivery requirements.
4. **Security services**
   - Stacks: [`live/foundation/security/us-east-1/cloudtrail`](../live/foundation/security/us-east-1/cloudtrail/terragrunt.hcl) and [`live/foundation/security/us-east-1/guardduty`](../live/foundation/security/us-east-1/guardduty/terragrunt.hcl); inventory wave marked `parallel: true`.
   - Dependency and gate: CloudTrail depends on the archive bucket in Terragrunt; GuardDuty has no Terragrunt dependency on CloudTrail. Verify Security account credentials and service prerequisites. The inventory records delegated-administrator registration as a separate management-account operation; no live stack implements it.
5. **Workload baselines**
   - Stacks: sandbox SCP attachments, security baseline, and test IAM roles. The inventory marks their wave `parallel: true`.
   - Paths: [`scp-attachments`](../live/workloads/sandbox-account/us-east-1/scp-attachments/terragrunt.hcl), [`security-baseline`](../live/workloads/sandbox-account/us-east-1/security-baseline/terragrunt.hcl), and [`test-iam-roles`](../live/workloads/sandbox-account/us-east-1/test-iam-roles/terragrunt.hcl).
   - Gate: inventory lists distinct prerequisites, but these leaves declare no Terragrunt dependency blocks. Verify sandbox target, management policy context, centralized security readiness, and exact read-only test-role trust and permissions. These are sandbox/test configurations, not evidence of production deployment.

Use the inventory's full stack IDs and `depends_on` values when selecting a stack in workflow inputs.

## Dependency matrix

| Stack | Depends on | Evidence and reason | Runtime gate |
| --- | --- | --- | --- |
| `backend-bootstrap` | None | Inventory bootstrap step; local-state stack. | Approved account/Region, key ARN, and bucket inputs; after creation, verify backend and migration prerequisites. |
| `management-github-oidc` | `backend-bootstrap` | Inventory-defined state prerequisite. | Remote state migrated; management account and provider credentials verified; OIDC subjects and least-privilege policies approved. |
| `log-archive-kms` | `backend-bootstrap` | Inventory-defined state prerequisite. | Remote state migrated; log archive account verified; administrators and service principals approved. |
| `management-scp` | `backend-bootstrap` | Inventory-defined state/security prerequisite. | Organizations feature set and management provider context verified; targets reviewed; unresolved IDs remain unattached. |
| `log-archive-bucket` | `backend-bootstrap`, `log-archive-kms` | Backend edge is inventory-defined. KMS edge is both inventory-defined and **Terragrunt-enforced** by the `kms` dependency block. | Key output available; Object Lock decision, retention, delivery principals, and bucket policy reviewed. |
| `security-cloudtrail` | `backend-bootstrap`, `log-archive-bucket` | Backend edge is inventory-defined. Bucket output edge is both inventory-defined and **Terragrunt-enforced** by the `log_archive_bucket` dependency block. | Security account verified; destination policy and Security-account key policy approved. |
| `security-guardduty` | `backend-bootstrap` | Inventory-defined state/security/operational prerequisite. | Security account and Organizations readiness verified; delegated administrator registration completed separately. |
| `sandbox-scp-attachments` | `backend-bootstrap`, `management-scp` | Inventory-defined state/security/operational prerequisites. | Sandbox ID resolved; management provider context, target, effective deny behavior, and break-glass path reviewed. |
| `sandbox-security-baseline` | `backend-bootstrap`, `security-guardduty`, `security-cloudtrail` | Inventory-defined state/security/logging/operational prerequisites. | Sandbox provider verified; centralized GuardDuty and CloudTrail readiness confirmed. |
| `sandbox-test-iam-roles` | `backend-bootstrap` | Inventory-defined state/identity prerequisite. | Sandbox ID resolved; exact repository subject and read-only permissions approved. |

Inventory dependency metadata is not equivalent to remote-state wiring or proof of a live service prerequisite. In particular, only the bucket-to-KMS and CloudTrail-to-bucket edges are explicit Terragrunt output dependencies among the foundation and workload leaves. Verify the remaining cross-stack readiness manually using approved runtime evidence before proceeding.

## Execution boundaries

### Bootstrap and state

The bootstrap stack deliberately excludes `live/_envcommon/remote-state.hcl`; its first state is local. Other normal leaves include the shared remote-state layer. The inventory describes backend creation followed by migration, and [`docs/bootstrap.md`](bootstrap.md) owns the detailed procedure.

The repository exposes these non-mutating preparation commands through `Taskfile.yml`:

```bash
task bootstrap:create-backend -- --dry-run
task bootstrap:create-backend -- --plan
task bootstrap:migrate-to-remote -- --list-stacks
task bootstrap:migrate-to-remote -- --plan
task bootstrap:migrate-to-remote -- --dry-run
```

The backend helper's `--apply` creates cloud resources. The migration helper's `--migrate` changes state placement. These are controlled, explicitly authorized operations, not routine validation. Follow the bootstrap guide and preserve its backups.

Stop on unresolved placeholders, identity/backend mismatches, failed checks, or migration errors. Do not start remote-state-backed stacks until the approved backend configuration is populated, backend checks pass, and the applicable state migration is complete.

### Planning and applying

`validate.yml` runs on pull requests, pushes to `main`, and manual dispatch. It performs formatting checks, SCP JSON validation, YAML and Markdown linting, and a local-render security-baseline check.

`security-scan.yml` runs on pull requests, pushes to `main`, a weekly schedule, and manual dispatch. It validates SCP JSON and the local baseline and runs configured security scanners. Neither workflow applies infrastructure. Check each workflow result for its scope and limitations.

`plan.yml` gives pull requests an inventory/selection metadata check without AWS access. For trusted `main` pushes or manual dispatch on `main`, its cloud job assumes the configured read-only identity and runs `task plan` across `live/`.

The plan runner uses `terragrunt run --all`; it is not a deployment-order executor. Plans are advisory, no saved-plan apply consumer exists, and no plan result authorizes mutation.

The default plan task can treat known placeholder or credential failures as success; the workflow invocation is not strict. A green result does not prove that every stack received a successful cloud plan.

`apply.yml` is explicitly a safe-skip workflow: it checks the reviewed revision, runs `task apply` with `APPLY=false`, supplies no AWS credentials, and does not deploy. The Taskfile has an enabling branch for `APPLY=true`, including a `run --all` path; that is not a safe sequential deployment orchestrator or the workflow's configured behavior.

The checked-in repository does not implement a routine applying workflow that consumes the inventory DAG and applies an exact reviewed saved plan. Do not treat the inventory, workflow name, or successful safe-skip as apply authorization.

`drift-detection.yml` runs weekly or by manual dispatch on `main` with a read-only role. Its script validates the inventory, then scans remote-state stacks serially in inventory order using read-only init/plan flags. It reports drift or operational errors; it does not repair resources.

`post-apply-verify.yml` is manually dispatched for one inventory stack and reviewed commit. Its script checks the selected stack and configured local security-baseline render, then reports live checks as pending; it does not prove deployed health.

### Validation gates and evidence

| Gate | Implementation | What a pass establishes | Limit and evidence |
| --- | --- | --- | --- |
| Repository/tool metadata | `task verify-env`; `scripts/tools/verify-env.py` | Local repository metadata and pinned tools satisfy that check. | Does not establish AWS identity, backend availability, or cloud posture. Retain command result if relevant. |
| Formatting, static validation, and policy JSON | `validate.yml`; corresponding `Taskfile.yml` tasks | The configured checks passed for the checked-out revision. | Local `validate:terraform` uses backend-disabled init/validate. It is not a cloud plan or runtime security proof. Retain PR/workflow result. |
| Security scans | `security-scan.yml`; `Taskfile.yml` | Configured scanner commands completed under their declared scope and thresholds. | Scans have exclusions and configuration limits; findings may require reviewed exceptions. Retain workflow result and sanitized disposition. |
| Inventory metadata | `plan.yml` metadata job; `scripts/ci/build-plan-matrix.py` | Discovered stack paths, inventory relationships, and owners pass parser checks. | It does not apply, expand changed selections to dependencies, or schedule a deployment. Retain job result. |
| Cloud planning | `plan.yml`; `scripts/ci/plan.py` | Only a successful strict plan run would establish successful plans for its invocation. | Current workflow uses default non-strict task behavior; known placeholder/credential failures may be tolerated. Plans are advisory and not saved for apply. Retain sanitized run summary; never publish raw state or plans. |
| Drift scan | `drift-detection.yml`; `scripts/ci/drift-ci.py` | The serial read-only scan reports no drift or errors for its selected remote-state stacks. | Does not remediate; access, backend, provider, and timeout failures are operational errors, not clean results. Retain workflow summary. |
| Post-apply check | `post-apply-verify.yml`; `scripts/ci/verify-post-apply.py`; `tests/smoke/verify-security-baseline.py` | Selected inventory scope and configured local baseline checks completed. | Live checks are reported pending; this is not runtime health evidence or proof of apply. Retain the summary and separately approved live verification evidence. |

## Safe operator sequence

1. **Review the change and scope.** Confirm the exact inventory stack IDs, paths, owners, account and Region catalog entries, module selection, and any relevant policy changes. Resolve placeholders through reviewed configuration; never guess IDs or backend values. Start with [`README.md`](../README.md), [`CONTRIBUTING.md`](../CONTRIBUTING.md), and [`SECURITY.md`](../SECURITY.md).
2. **Check the execution path and prerequisites.** Confirm required workflow checks and protections are available. For initial bootstrap or state migration, follow [`docs/bootstrap.md`](bootstrap.md) and its controlled-operation requirements. Confirm identity and target context using approved means without printing credentials or sensitive identifiers.
3. **Run non-mutating validation.** Use the repository's `task validate`, lint, and security-scan workflows as applicable. For a scoped local Terraform validation, `task validate:terraform TARGET=live/.../stack` uses backend-disabled init; check `Taskfile.yml` before selecting a target. Record the revision and result.
4. **Review plans and upstream readiness.** Use the read-only planning workflow and relevant inventory readiness checks. Examine account, Region, state, policy, encryption, replacement, and cross-account effects in the trusted environment. A plan is advisory and must not be substituted for an approved deployment artifact.
5. **Stop on a failed or ambiguous prerequisite.** Do not proceed downstream after a failed upstream change, a missing dependency output, a failed plan, an identity or state mismatch, or an unresolved live gate. Follow repository change-management and incident procedures; this repository does not define destructive rollback commands.
6. **Perform mutation only through a separately approved procedure.** The checked-in apply workflow does not apply infrastructure. Until a reviewed deployment workflow consumes the order and applies the exact approved plan, there is no repository-defined routine apply command to recommend. Bootstrap creation and state migration remain separately scoped controlled exceptions.
7. **Verify and record outcomes.** Run the post-apply workflow for the exact inventory stack where applicable, then complete its pending live checks with authorized runtime evidence. Record the commit, stack ID, workflow run, approval/change reference, sanitized plan summary, verification result, and follow-up. Do not store credentials, raw state, or sensitive plan artifacts in documentation or issues.

## Parallelism and failure handling

The inventory marks four multi-stack waves as parallel. The plan-matrix script checks dependency placement in earlier phases/waves but only selects plan targets; it does not execute applies. Terragrunt can enforce the two output dependencies identified above. Drift scans one stack at a time, and no workflow applies inventory waves.

Parallel applies are not established as safe by repository execution tooling. Serialize mutation as a safety recommendation, avoid overlapping operations on the same state, and coordinate shared foundation, account-policy, identity, and backend changes.

For validation, dependency, plan, apply, verification, lock, drift, or policy failures, stop the affected sequence. Preserve logs and migration backups, identify the failing stack and state boundary, and use the repository's reviewed change-management or incident process. Do not apply downstream stacks after an upstream failure.

Do not delete or manually edit state, bypass locking, force-unlock without documented authorization, detach security policies, or improvise rollback commands. No general rollback procedure is defined here; recovery must be explicitly scoped and approved.

## Environment and state safeguards

- Resolve account and Region from the live account/Region catalogs and each leaf's inherited context. Confirm the actual caller and target with the approved identity process before any cloud operation. Never rely on ambient credentials as evidence of the intended account.
- Normal leaves compose root/catalog locals with `account.hcl` and `region.hcl`; shared `_envcommon` layers generate provider, remote-state, and tags. The bootstrap leaf uses a separately generated provider and local state. Review rendered configuration when context is unclear.
- Protect remote state and plans as sensitive operational data. Use approved short-lived, least-privilege identities and repository-defined state locking/concurrency controls. Never place credentials in source control, command output, or deployment evidence.
- Organization SCPs, KMS policy, logging destinations, and identity trust have cross-account effects. Review target scope, effective policy, exception paths, and service access before any approved mutation.

## Ownership and maintenance

Use [`inventory/stack-owners.yaml`](../inventory/stack-owners.yaml) and [`CODEOWNERS`](../CODEOWNERS) for review routing. When stack paths, dependencies, phase/wave boundaries, readiness checks, or workflow behavior change, update this guide and authoritative configuration in the same reviewed change.

Tie claims about deployment, runtime health, and drift to dated, sanitized runtime evidence.

## Related references

- [Repository overview](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/README.md)
- [Bootstrap and state migration](bootstrap.md)
- [Live configuration guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/README.md)
- [Workload configuration guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/workloads/README.md)
- [Deployment inventory](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/deployment-order.yaml)
- [Stack owners](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/stack-owners.yaml)
- [Task definitions](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Taskfile.yml)
- [Planning workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/plan.yml), [safe-skip apply workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/apply.yml), [drift workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/drift-detection.yml), and [post-apply workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/post-apply-verify.yml)
- [Smoke-test guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/README.md) and [security-baseline checklist](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/smoke/security-baseline-checklist.md)
