# Bootstrap Guide

## Purpose

Bootstrap establishes the remote Terraform state backend before normal live
stacks are operated. In this repository, `live/bootstrap/backend-bootstrap`
creates the backend while using local state; a separate helper then migrates
eligible live stacks to the configured remote backend. The bootstrap stack is
excluded from the shared remote-state include so it does not depend on the
backend it is responsible for creating.

This guide is for authorized platform engineers and infrastructure operators.
It covers local tool preparation, backend creation, and state migration. It
does not authorize infrastructure changes. Normal foundation and workload
operations follow the repository's deployment inventory and execution policy.

> [!IMPORTANT]
> **Bootstrap is not currently ready to apply from this checkout.** Account
> entries contain unresolved values, and `live/common.hcl` does not define the
> backend bootstrap metadata required by the helper. The backend helper refuses
> apply while required values are unresolved; the migration helper refuses
> migration until concrete backend metadata is present. Do not guess values or
> proceed around these checks. Resolve configuration through the repository's
> review and change process first.

## Scope and boundaries

The verified workflow is: prepare the local tools, review and configure the
bootstrap inputs, create the backend using the bootstrap stack's local state,
then migrate selected consuming stacks to remote state. The repository does
not provide a separate backend-output export command. Review approved backend
outputs and populate the repository's designated configuration through a
reviewed change before migration.

The [deployment inventory](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/deployment-order.yaml) places backend
creation and state migration before foundation and workload phases. Use it as
the source for stack dependencies, readiness conditions, and deployment order.
The [repository execution policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/README.md#infrastructure-execution-policy)
requires workflow execution for routine infrastructure changes. Initial
backend creation and state migration are controlled exceptions and require
separate authorization and safeguards described there; they do not authorize
direct deployment of unrelated stacks.

## Architecture overview

```text
backend-bootstrap stack (local state)
              │ creates
              ▼
approved remote backend configuration
              │ consumed by
              ▼
live stacks ── migration helper ──> remote state
```

The backend bootstrap stack does not include
`live/_envcommon/remote-state.hcl`. Other stacks generate an S3 backend
configuration from `live/common.hcl` and the stack hierarchy. The configured
backend uses encryption, a customer-managed KMS key, and DynamoDB locking.
State keys include the path-relative stack identity. Configuration has no
empty/local fallback: missing backend values prevent safe initialization.

The root Terragrunt configuration exposes shared catalog data but does not
itself define a provider or backend. Account and Region context is read from
the applicable catalog and `account.hcl` / `region.hcl` files; the bootstrap
stack has its own provider configuration because it is outside the normal
account/Region hierarchy.

## Prerequisites

- A checkout of this repository and the repository's Task runner (`task`).
  `Taskfile.yml` is authoritative for task behavior; `justfile` and `Makefile`
  delegate to it.
- The pinned tool versions in `tooling/.tool-versions`, including Terraform,
  Terragrunt, Python, AWS CLI, and Task. Terraform and Terragrunt pins are also
  recorded in `tooling/.terraform-version` and
  `tooling/.terragrunt-version`.
- For helper execution, Python and the executables required by that mode must
  be available on `PATH`: the backend helper uses Terraform and Terragrunt;
  migration uses Terragrunt and AWS CLI when migrating. The migration helper
  uses AWS STS and read-only S3/DynamoDB inspection before making changes.
- Approved, concrete account, Region, backend, module, and encryption-key
  configuration. The current checkout does not meet this prerequisite.
- An authorized AWS credential context for the intended account and Region.
  The migration helper checks the caller identity and rejects an environment
  Region that conflicts with configured backend Region. Never put credentials
  in repository files or command arguments.
- For actual backend creation or state migration, an explicitly authorized
  change/maintenance procedure, reviewed target and inputs, and no conflicting
  Terraform/Terragrunt operation against the affected state.

### Prepare and verify tools

The setup wrappers are platform-specific. On Linux or macOS:

```bash
./scripts/cross-platform/setup.sh
```

On Windows PowerShell:

```powershell
.\scripts\cross-platform\setup.ps1
```

These wrappers delegate setup to `scripts/cross-platform/setup.py`, which
routes to the OS-specific Go installer. The installer uses the inventory in
`tooling/.tool-versions` to install and verify the pinned tools using its
supported package-manager paths. Setup may install tools and make system or
network changes; review the installer behavior before running it. The tool
versions, cross-platform mirror, and Go version are checked against
`tooling/.tool-versions`, `tooling/cross-platform/asdf-tool-versions`, and
`go.mod`.

After the required tools are installed, run the read-only repository verifier:

```bash
task verify-env
```

It checks repository tool-version metadata and installed tools. It does not
validate AWS authorization, backend readiness, or cloud posture. For a
non-mutating preview of the setup wrapper's actions, use the platform wrapper
with `--dry-run`; the wrapper still needs a usable Python interpreter to run
its source-of-truth Python script.

## Before you begin: safety and change control

- Confirm written authorization, the intended account/Region, and the exact
  scope of the bootstrap or maintenance operation using approved procedures.
- Review the deployment inventory, bootstrap and migration scripts, current
  state ownership, and the repository execution policy.
- Confirm no other operator, workflow, or Terraform/Terragrunt process is
  operating on the selected stack or state.
- Resolve all placeholders only through approved, reviewed configuration.
  Do not infer backend values from ambient credentials or guess identifiers.
- Protect state and any backups as sensitive data. Do not commit state, local
  credentials, plan files, or generated files.
- Treat backend creation as a cloud mutation and migration as a state-changing
  operation. Migration is not documented as reversible; unexpected errors
  require stopping and review before any retry or recovery action.

## Bootstrap workflow

Commands below use Task's `CLI_ARGS` forwarding, as defined in `Taskfile.yml`.
Read-only commands do not grant authorization for later mutation.

### 1. Check repository environment — read-only

```bash
task verify-env
```

Resolve any missing or mismatched tool reports against the pins in `tooling/`.
This checks local tools and repository metadata only; it does not check AWS
credentials or cloud resources.

### 2. Review bootstrap configuration — read-only

Inspect the bootstrap stack, root/shared Terragrunt configuration, account and
Region catalogs, module catalog, and state configuration. Confirm approved
values exist and agree across the sources before continuing. Relevant files
are linked below.

The checked-in values currently fail readiness: account IDs are placeholders,
and `live/common.hcl` has no concrete bootstrap/backend projection. Therefore
the next command is for local preview only; a usable plan and any apply must
wait for reviewed configuration.

### 3. Preview backend helper — read-only

```bash
task bootstrap:create-backend -- --dry-run
```

The helper checks required repository files and unresolved values and prints
the intended Terragrunt commands without running Terraform. It checks for the
Terraform and Terragrunt executables unless `--skip-tool-check` is supplied.
It does not prove that AWS permissions, backend resources, or the plan are
valid.

After configuration has been approved and resolved, an operator may create a
plan with:

```bash
task bootstrap:create-backend -- --plan
```

This runs `terragrunt init --backend=false`, `terragrunt validate`, and
`terragrunt plan` in the bootstrap stack. It is a planning operation, not an
apply, but it can make read requests using the active AWS context. Review the
plan and target before proceeding. Do not use `--allow-unresolved-tbd` as a
path to apply; the helper explicitly prohibits unresolved values for apply.

### 4. Create the backend — **CLOUD MUTATION**

Only under the separately authorized initial-bootstrap exception described in
the [execution policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/README.md#controlled-exceptions), and only after
review of the exact plan, target account, Region, and recovery approach:

```bash
task bootstrap:create-backend -- --apply
```

The helper prompts for the literal response `yes` before it runs
`terragrunt apply -auto-approve`. In non-interactive mode, `--yes` is also
required. The helper's confirmation is not an approval workflow and does not
replace authorization. Its timeout defaults to 900 seconds per Terragrunt
command. Stop if the helper reports unresolved configuration, an unexpected
identity, an unexpected plan, or any command failure. Review the resulting
backend outputs securely; do not paste sensitive values into tickets or logs.

### 5. Inspect migration candidates — read-only

After the backend exists and approved backend configuration is committed,
first list discovered non-bootstrap stacks and classifications:

```bash
task bootstrap:migrate-to-remote -- --list-stacks
```

Then review candidates without mutation:

```bash
task bootstrap:migrate-to-remote -- --plan
```

`--dry-run` is also supported and reports candidates without creating backup
copies or running migration. `--list-stacks`, `--plan`, and `--dry-run` do not
validate live backend readiness or caller identity as the actual migration
mode does. Check each selected stack against the inventory and approved
maintenance scope.

### 6. Migrate selected state — **STATE MUTATION**

The migration helper, by default, discovers all non-bootstrap Terragrunt
stacks. For controlled scope, pass one or more reviewed stack paths with
`--stack`. `[REVIEWED_STACK_PATH]` below is a required operator input, not a
literal path:

```bash
task bootstrap:migrate-to-remote -- --migrate --stack [REVIEWED_STACK_PATH]
```

The helper validates concrete backend metadata, checks the AWS caller identity
and backend Region, and reads the backend bucket's location, versioning,
encryption and public-access-block settings plus lock-table existence. It then
prompts for `yes` before migration. In non-interactive mode, `--yes` is
required. For each eligible stack, it copies local state and related Terraform
metadata to `.bootstrap-backups`, runs `terragrunt init -migrate-state`, then
runs `terragrunt state pull` and checks generated backend metadata. It keeps
the local recovery artifacts; it does not claim migration can be reversed.

The helper takes a repository-local process lock to prevent a second instance
of this helper. That lock does not prevent unrelated Terraform or workflow
activity. Ensure all other operations are stopped independently. Do not
manually edit or delete state, overwrite remote state, force-unlock, run
simultaneous migrations, or change backend configuration ad hoc. If migration,
backup, or verification fails or is interrupted, retain all local state and
backups and stop for owner review; do not retry blindly.

The stack path argument can be repeated. Selection filters `--include` and
`--exclude`, and execution behavior `--keep-going`/`--fail-fast` are available
in the script, but use them only when specifically reviewed for the approved
maintenance scope. The default migration behavior is fail-fast.

### 7. Continue in inventory order

Only after the selected stack's migration reports success and its remote state
has been verified should normal remote-state operations proceed. Follow the
phases, dependencies, readiness requirements, approvals, and checks in
[`inventory/deployment-order.yaml`](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/deployment-order.yaml).
Routine infrastructure changes follow the approved GitHub Actions path and
repository change policy; this guide does not provide an apply command for
foundation or workload stacks. The checked-in `apply.yml` workflow currently
runs the Task apply target in its configured safe-skip mode and explicitly
reports that a real apply was skipped. No checked-in workflow step provisions
the bootstrap backend. Do not interpret a successful safe-skip run, plan, or
validation workflow as evidence that bootstrap or an infrastructure apply
occurred.

## Post-bootstrap verification

Use the following evidence at the appropriate stage:

| Check | What it establishes | What it does not establish |
| --- | --- | --- |
| `task verify-env` | Local repository metadata and pinned tool availability | AWS identity, backend existence, or infrastructure posture |
| Migration helper `--migrate` completion | The helper observed configured S3 backend metadata and successfully ran `state pull` for migrated stacks | Application-level health or the correctness of all infrastructure resources |
| `task lint:markdown` | Markdown lint results for repository Markdown | MkDocs site build, infrastructure validity, or cloud state |
| GitHub Actions validation workflow | The workflow's configured static checks for that revision | Successful bootstrap or live cloud verification |

The migration command's success output and protected workflow/check results are
appropriate non-sensitive evidence to retain with the approved change record.
Do not attach state snapshots, credentials, or sensitive plan output. The
post-apply workflow is manually triggered and its verifier can report live
checks as pending; it is not automatic proof that bootstrap succeeded. The
local security-baseline smoke checker reports rendered configuration, not
live AWS posture.

## Troubleshooting and failure handling

| Symptom | Safe response |
| --- | --- |
| Helper reports unresolved values or missing backend metadata | Stop. Resolve the relevant catalog/configuration through review; do not guess values or enable an apply with placeholders. |
| Tool missing or version check fails | Run `task verify-env`, compare with `tooling/.tool-versions`, and use the repository setup instructions for the required tool. |
| Credentials missing, invalid, or access denied | Stop and obtain the approved identity/permissions for the target. Never copy credentials into repository files or command history. |
| Backend bucket/table missing or checks fail | Stop and compare the approved backend configuration with bootstrap outputs and target account/Region. Do not create or alter resources manually as a workaround. |
| Migration lock exists | Confirm no migration helper is still active and escalate to the stack owner. Do not remove the lock or force-unlock without an explicitly reviewed recovery procedure. |
| Backup, migration, or post-migration verification fails | Retain local state and backup files, prevent further operations against the affected state, and seek owner review before retry or recovery. |
| Terragrunt plan/validation fails | Preserve the command error without sharing secrets; review the selected stack configuration and dependency readiness, then seek owner review if the cause is unclear. |
| CI validation fails | Use the failing workflow/job output and fix the reviewed change. Do not bypass validation or infer that cloud bootstrap ran. |

Bootstrap stack ownership is listed in
[`inventory/stack-owners.yaml`](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/stack-owners.yaml). Follow the
repository's [security policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/SECURITY.md) for security issues.

## Operational guardrails

- Use repository-defined scripts and Task targets; do not improvise backend
  configuration or cloud commands.
- Do not alter cloud resources outside the approved workflow or an explicitly
  authorized bootstrap/maintenance procedure.
- Never commit credentials, state, backups, local plans, or sensitive generated
  files.
- Do not bypass review, CI checks, IAM boundaries, service control policies,
  state locking, or change approvals.
- Do not use production credentials for unreviewed experiments.
- Do not run concurrent bootstrap or state migrations.
- Keep non-sensitive completion evidence with the approved change record.

## Related documentation and implementation

- [Repository overview and execution policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/README.md)
- [Live infrastructure overview](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/README.md)
- [Deployment order and readiness inventory](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/deployment-order.yaml)
- [Stack owners](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/inventory/stack-owners.yaml)
- [Security policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/SECURITY.md)
- [Contribution and review guidance](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/CONTRIBUTING.md)
- [Test and verification guidance](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/README.md)
- [Backend creation helper](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/bootstrap/01-create-backend.py)
- [State migration helper](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/bootstrap/02-migrate-to-remote.py)
- [Backend bootstrap Terragrunt stack](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/bootstrap/backend-bootstrap/terragrunt.hcl)
- [Shared remote-state configuration](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/_envcommon/remote-state.hcl)
- [Shared live configuration](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/common.hcl) and [root Terragrunt configuration](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/terragrunt.hcl)
- [Task definitions](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Taskfile.yml), [tool pins](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tooling/.tool-versions), and [environment verifier](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/tools/verify-env.py)
