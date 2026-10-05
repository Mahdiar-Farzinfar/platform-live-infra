# Live Infrastructure Configuration

`live/` contains this repository's Terragrunt configuration for selecting AWS
account and Region context, composing shared settings, and defining deployable
stacks. It is the live configuration layer, not a library of reusable Terraform
resources. Reusable modules are referenced from the companion repository
declared in [`catalogs/module-versions.hcl`](catalogs/module-versions.hcl).

Operational policy and implementation status are described in the repository
[`README.md`](../README.md), contribution guidance in
[`CONTRIBUTING.md`](../CONTRIBUTING.md), and security guidance in
[`SECURITY.md`](../SECURITY.md). The deployment sequence is maintained in
[`inventory/deployment-order.yaml`](../inventory/deployment-order.yaml).

## Directory layout

```text
live/
├── terragrunt.hcl                 # Root locals and exposed common catalog contract
├── common.hcl                     # Catalog reads and normalized projections
├── catalogs/                      # Account, Region, tag, and module metadata
├── _envcommon/                    # Shared provider, remote-state, and tag config
├── bootstrap/backend-bootstrap/   # Backend bootstrap stack (local state initially)
├── foundation/                    # Management, log-archive, and security stacks
└── workloads/                     # Workload account stacks
```

Deployable leaves follow an account and Region hierarchy where applicable:
account metadata is in `account.hcl`, Region metadata is in `region.hcl`, and
each stack leaf has its own `terragrunt.hcl`. Current leaves and their ordering
are listed in the deployment inventory; this overview intentionally avoids
duplicating that inventory.

## Configuration composition

- [`terragrunt.hcl`](terragrunt.hcl) is the root Terragrunt configuration. It
  reads `common.hcl` and exposes named locals for the common catalog
  projections. It does not define provider or remote-state configuration.
- [`common.hcl`](common.hcl) reads the account, Region, tags, and module-version
  catalogs. It exposes normalized account/Region metadata, tag projections,
  and constructed module sources, versions, and requirements.
- [`catalogs/accounts.hcl`](catalogs/accounts.hcl) and
  [`catalogs/regions.hcl`](catalogs/regions.hcl) hold account and Region
  metadata. Current account IDs are placeholders; the Region catalog currently
  defines `us-east-1` as enabled and primary.
- [`catalogs/tags.hcl`](catalogs/tags.hcl) supplies common and contextual tag
  maps. [`_envcommon/tagging.hcl`](_envcommon/tagging.hcl) composes stack tags
  and passes them as module inputs.
- [`catalogs/module-versions.hcl`](catalogs/module-versions.hcl) is the central catalog for module version management. It defines versioned Git module source references from module names, module paths, and approved refs,
 and records the expected immutable commit SHA (`digest`) for each module release. The digest values identify the exact commits associated with the approved module versions and must be enforced by the module source configuration or CI/CD validation to provide effective commit-level pinning.
- [`_envcommon/provider.hcl`](_envcommon/provider.hcl) generates the AWS
  provider configuration from the consuming account and Region context.
  Individual leaves include the shared files they need; the root does not
  automatically include provider, state, or tagging layers.
- [`_envcommon/remote-state.hcl`](_envcommon/remote-state.hcl) defines an
  encrypted S3 remote-state backend and derives its state key from the stack
  path. Backend metadata is read from common configuration and is currently
  absent from the catalogs, so backend initialization is not ready until
  approved values are supplied.
- Stack `terragrunt.hcl` files select a catalog module source and inputs.
  Some declare Terragrunt `dependency` blocks to consume outputs from another
  stack; consult the leaf and the deployment inventory for those relationships.

## Deployment topology and layering

The current configuration has three operational layers: backend bootstrap,
foundation stacks, and workload stacks. The authoritative sequence, phases,
waves, dependencies, readiness conditions, and checks are in
[`inventory/deployment-order.yaml`](../inventory/deployment-order.yaml). Follow
that inventory and the operational policy in the root README; directory names
or lexical path order do not establish a safe deployment sequence.

The inventory describes bootstrap with local state followed by an explicit
local-to-remote migration. Foundation waves establish prerequisites before
governance, centralized storage, and security services; workload stacks follow
those phases. Do not assume that a broad recursive Terragrunt command is a safe
deployment method.

## Prerequisites and local setup

Tool versions are recorded in [`../tooling/.terraform-version`](../tooling/.terraform-version),
[`../tooling/.terragrunt-version`](../tooling/.terragrunt-version), and
[`../tooling/.tool-versions`](../tooling/.tool-versions). The cross-platform
version mirror is [`../tooling/cross-platform/asdf-tool-versions`](../tooling/cross-platform/asdf-tool-versions).
Use the repository setup wrappers, which delegate to the shared setup
implementation:

- POSIX (Linux/macOS): [`../scripts/cross-platform/setup.sh`](../scripts/cross-platform/setup.sh)
- Windows PowerShell: [`../scripts/cross-platform/setup.ps1`](../scripts/cross-platform/setup.ps1)

The Dev Container definition is in
[`.devcontainer/devcontainer.json`](../.devcontainer/devcontainer.json).
To verify the local environment through the repository task interface, run
from the repository root:

```sh
task verify-env
```

For available tasks and their behavior, consult [`../Taskfile.yml`](../Taskfile.yml).
The account and backend catalogs contain unresolved placeholders. The
configuration also does not document a completed local AWS authentication or
role-assumption procedure; use only an independently approved identity and
follow the repository's deployment policy.

## Safe operational workflow

1. Set up the pinned toolchain and run `task verify-env` from the repository
   root.
2. Read the repository README and inspect the target stack's entry in
   `inventory/deployment-order.yaml` and `inventory/stack-owners.yaml`.
3. Review the leaf configuration, its account and Region metadata, and every
   included shared layer or dependency.
4. Run repository validation from the root with `task validate`. This performs
   the repository's configured non-cloud checks; consult the Taskfile for its
   exact scope.
5. Treat any plan as advisory and review its target context and changes
   carefully. The `plan` workflow provides cloud plans only on trusted `main`
   runs; pull requests receive metadata validation without AWS access. The
   plans are not saved deployment artifacts and do not authorize an apply.
6. Follow the deployment and exception requirements in the root README. The
   checked-in `apply.yml` currently runs the Task apply command with applying
   disabled; it is an intentional safe skip, not an infrastructure deployment
   workflow. Although the root README describes the required workflow-based
   deployment policy, the checked-in workflows do not currently implement a
   functional infrastructure apply path.
7. Where applicable, consult the post-apply workflow and drift workflow logs.
   The post-apply workflow checks inventory/configuration and reports live
   checks as pending; it does not itself establish live infrastructure status.

Never apply an unreviewed plan, bypass required review or workflow controls,
run broad recursive operations without explicit authorization and documented
scope, or alter remote state manually. State-changing bootstrap, migration,
recovery, and deployment actions require the approved procedure described in
the root README. Do not infer that an apply path is operational merely because
a task or workflow file exists.

## State management and bootstrap

The bootstrap leaf at
[`bootstrap/backend-bootstrap/terragrunt.hcl`](bootstrap/backend-bootstrap/terragrunt.hcl)
deliberately omits the shared remote-state include because the backend must
exist before normal stacks can use it. Normal leaves that include
[`_envcommon/remote-state.hcl`](_envcommon/remote-state.hcl) use the configured
S3 backend, encryption, KMS key, and DynamoDB lock table. Those backend values
are not populated in the current common catalog. Do not initialize or migrate
state on the assumption that the backend is ready.

The repository's actual bootstrap scripts are under
[`../scripts/bootstrap/`](../scripts/bootstrap/), and the task wrappers are
defined in [`../Taskfile.yml`](../Taskfile.yml). The detailed bootstrap and
state-management runbooks referenced by older documentation are not present in
this checkout. Until authoritative procedures are added, use the repository
README and inventory as the available references and obtain the approved
procedure from the accountable maintainer. Do not manually edit state or
invent bucket, key, or recovery settings.

## Ownership, change management, and CI/CD

[`../inventory/stack-owners.yaml`](../inventory/stack-owners.yaml) maps current
deployable stack paths to owners. [`../CODEOWNERS`](../CODEOWNERS) provides
repository path ownership, and [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
describes contribution expectations.

The checked-in workflows provide distinct checks:

- [`validate.yml`](../.github/workflows/validate.yml) runs formatting,
  validation, linting, and the configured security-baseline check.
- [`plan.yml`](../.github/workflows/plan.yml) validates planning metadata for
  pull requests and runs read-only plans on trusted `main`; its results are
  advisory and are not a saved-plan/apply pipeline.
- [`apply.yml`](../.github/workflows/apply.yml) intentionally sets `APPLY` to
  false and supplies no AWS credentials, so it does not deploy infrastructure.
- [`drift-detection.yml`](../.github/workflows/drift-detection.yml) defines a
  scheduled/manual read-only drift scan on `main`.
- [`post-apply-verify.yml`](../.github/workflows/post-apply-verify.yml)
  validates the selected inventory scope and configured baseline, while
  explicitly leaving live checks pending.

Workflow files do not prove that repository/environment protection rules or
cloud-side permissions are configured. Follow the policy and status
limitations documented in [`../README.md`](../README.md).

## Security and operational guardrails

- Never commit credentials, tokens, private keys, or generated state and plan
  data. Follow [`../SECURITY.md`](../SECURITY.md) for security reporting and
  incident guidance.
- Use only approved, least-privilege AWS identities and verify the intended
  account, Region, and state context before cloud access.
- Respect backend encryption and locking settings; do not bypass state
  controls or perform undocumented state maintenance.
- Review module-source and workflow changes as infrastructure changes. Use
  repository-defined validation and scanning through the Taskfile where
  appropriate.
- The repository includes SCP policy documents under
  [`../policies/scp/`](../policies/scp/) and stacks referencing SCPs. Their
  presence does not establish that policies have been deployed or are enforced.

## Troubleshooting and authoritative references

Start with the setup wrappers and `task verify-env` for toolchain issues. For
stack selection and sequencing, consult the deployment-order inventory; for
ownership, consult the stack-owners inventory and CODEOWNERS. For CI behavior,
inspect the relevant workflow run and its logs. For security concerns, follow
[`../SECURITY.md`](../SECURITY.md). Bootstrap, state migration, recovery, and operational procedures are documented
in the repository’s `docs/` directory and are published on the project
documentation site. Refer to the applicable documentation for each activity:

- [`../docs/bootstrap.md`](../docs/bootstrap.md) for backend bootstrap and initial setup.
- [`../docs/state-management.md`](../docs/state-management.md) for state initialization, migration, recovery, and remote-state operations.
- [`../docs/deployment-order.md`](../docs/deployment-order.md) for deployment sequencing, phases, and dependency ordering.
- [`../docs/operations.md`](../docs/operations.md) for operational procedures and runbooks.
- [`../docs/cross-platform.md`](../docs/cross-platform.md) for cross-platform environment setup and execution guidance.
- [`../docs/index.md`](../docs/index.md) for the documentation portal entry point and links to the published documentation site.

Always validate an intended procedure against the current repository
configuration, deployment inventory, and applicable operational policy before
performing state-changing actions.

## Related documentation

- [Repository overview and operating policy](../README.md)
- [Contribution guidance](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Deployment-order inventory](../inventory/deployment-order.yaml)
- [Stack ownership inventory](../inventory/stack-owners.yaml)
- [Task definitions](../Taskfile.yml)
- [Workflows](../.github/workflows/)
