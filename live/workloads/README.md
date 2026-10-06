# Workload Infrastructure

## Purpose

`live/workloads/` contains live Terragrunt configuration for workload-account
stacks. In the checked-out tree it covers the `sandbox-account` account and
its `us-east-1` region, with stacks for SCP attachment, a GuardDuty security
baseline, and IAM validation roles. It is a live-configuration layer, not a
catalog of reusable Terraform modules: leaf configurations select shared
module sources and provide stack inputs. Reusable module implementations are
maintained separately; see the [repository overview](../../README.md).

This layer sits alongside, rather than replaces, [`live/bootstrap/`](../README.md)
and `live/foundation/`. Bootstrap establishes the state backend; foundation
stacks configure platform-wide management, logging, and security capabilities.
Workload stacks configure account-level controls and services that consume or
depend on those capabilities. The [live-layer guide](../README.md) describes
the broader hierarchy.

Platform infrastructure contributors and the listed stack owners should use
this directory when reviewing or changing workload account, region, or stack
configuration. Account metadata is in `account.hcl`, regional metadata is in
`region.hcl`, and each deployable leaf has a `terragrunt.hcl`.

## Before You Change Anything

- Read the [repository overview](../../README.md) and [live-layer guide](../README.md).
- Find the stack owner in [`inventory/stack-owners.yaml`](../../inventory/stack-owners.yaml)
  and check prerequisites and ordering in
  [`inventory/deployment-order.yaml`](../../inventory/deployment-order.yaml).
- Follow [`CONTRIBUTING.md`](../../CONTRIBUTING.md) and
  [`SECURITY.md`](../../SECURITY.md); use the documented
  [tool setup](../../scripts/cross-platform/).
- Review the relevant plan and use only the repository's documented,
  authorized delivery process. The current apply workflow explicitly runs a
  safe skip; it is not an infrastructure deployment.

Operational guardrails:

- Do not apply unreviewed infrastructure changes or bypass applicable
  repository, pull-request, workflow, or approval controls.
- Do not manually edit remote state or run broad recursive Terragrunt
  operations unless an explicitly documented and authorized procedure calls
  for them.
- Do not commit credentials, secrets, access keys, private keys, sensitive
  plans, or state artifacts. Use least-privilege access and the repository's
  documented authentication process.

## Directory Layout

```text
workloads/
└── sandbox-account/
    ├── account.hcl
    └── us-east-1/
        ├── region.hcl
        ├── scp-attachments/
        │   └── terragrunt.hcl
        ├── security-baseline/
        │   └── terragrunt.hcl
        └── test-iam-roles/
            └── terragrunt.hcl
```

The account and region files project metadata and do not themselves declare
resources. The leaf configurations select modules and inputs.

## Current Workload Stacks

The names and intended roles of the three stacks are described in their
configuration:

| Stack | Configured responsibility | Owner source |
| --- | --- | --- |
| `scp-attachments` | Create the sandbox region-restriction SCP and target the sandbox account when its catalog ID is valid. | [`stack-owners.yaml`](../../inventory/stack-owners.yaml) |
| `security-baseline` | Configure the account-local GuardDuty detector and protection features. | [`stack-owners.yaml`](../../inventory/stack-owners.yaml) |
| `test-iam-roles` | Configure the sandbox GitHub OIDC provider and a repository-scoped, read-only IAM validation role. | [`stack-owners.yaml`](../../inventory/stack-owners.yaml) |

The account catalog currently contains placeholder account identifiers. The
stack configurations use unresolved sentinels or empty target lists in those
cases; do not infer account IDs or treat the configuration as evidence of
deployed resources.

## Configuration Composition Model

The workload hierarchy composes catalog metadata with shared live settings
and leaf inputs:

```text
live/terragrunt.hcl and live/common.hcl catalog projections
  → workload account.hcl
  → regional region.hcl
  → leaf terragrunt.hcl and included shared layers
```

- [`live/terragrunt.hcl`](../terragrunt.hcl) reads shared locals and exposes
  projections; it deliberately does not define the provider or remote state.
- [`live/common.hcl`](../common.hcl) loads the account, region, tag, and
  module-version catalogs under [`live/catalogs/`](../catalogs/).
- `sandbox-account/account.hcl` maps the hierarchy key `sandbox-account` to
  the catalog key `sandbox` and exposes account context to descendants.
- `sandbox-account/us-east-1/region.hcl` projects the region catalog entry and
  records whether the region is enabled for this account.
- Stack files include the regional context and shared layers as needed:
  [`provider.hcl`](../_envcommon/provider.hcl) generates AWS provider
  configuration; [`remote-state.hcl`](../_envcommon/remote-state.hcl)
  configures remote state for normal stacks; and
  [`tagging.hcl`](../_envcommon/tagging.hcl) composes catalog and context tags.
  The `scp-attachments` and `test-iam-roles` leaves generate stack-specific
  provider blocks because their account-targeting requirements differ.
- Each leaf reads `module_sources` projected from
  [`module-versions.hcl`](../catalogs/module-versions.hcl) through
  `common.hcl`, then supplies stack-specific inputs. Inspect the leaf file for
  the exact module key and behavior.

The backend-bootstrap stack is outside this directory and intentionally uses
local state before the backend exists. The shared remote-state layer and
bootstrap procedure are described in the [live-layer guide](../README.md).

## Deployment Order and Dependencies

The authoritative inventory is
[`inventory/deployment-order.yaml`](../../inventory/deployment-order.yaml).
All three workload stacks are in the `workload-baselines` phase and
`sandbox-baseline-and-identity` wave. Their explicit prerequisites differ:

- `scp-attachments` depends on `backend-bootstrap` and `management-scp`.
- `security-baseline` depends on `backend-bootstrap`, `security-guardduty`,
  and `security-cloudtrail`.
- `test-iam-roles` depends on `backend-bootstrap`.

The inventory lists manual approval and readiness requirements for each
stack; consult it for the full deployment order and checks. A shared wave or
similar stack names do not remove those dependencies. Do not infer that
recursive execution is safe from directory layout alone.

## Validation, Planning, and Delivery

The repository's [`Taskfile.yml`](../../Taskfile.yml) defines formatting,
Terragrunt and Terraform validation, YAML and Markdown linting, policy JSON
validation, and local security-baseline configuration checks. Repository-wide
Terragrunt operations default to the full `live/` tree; review task scope
before running them and use an explicit target when supported. The README
does not prescribe unverified stack commands.

The configured workflows provide these checks and boundaries:

- [`validate.yml`](../../.github/workflows/validate.yml) runs on pull
  requests, pushes to `main`, and manual dispatch; it checks formatting,
  policy JSON, YAML, Markdown, and locally rendered baseline configuration.
- [`plan.yml`](../../.github/workflows/plan.yml) validates planning metadata
  for pull requests. Cloud-capable plans are limited by workflow conditions
  to trusted `main` runs; its comments state that this workflow does not
  implement the saved-plan/apply deployment policy.
- [`apply.yml`](../../.github/workflows/apply.yml) currently invokes the
  repository apply task with `APPLY=false` and supplies no AWS credentials.
  It explicitly does not deploy infrastructure.
- [`drift-detection.yml`](../../.github/workflows/drift-detection.yml)
  supports scheduled and manual read-only drift scans on `main`.
- [`post-apply-verify.yml`](../../.github/workflows/post-apply-verify.yml)
  is manually dispatched for one inventory stack; see the workflow and
  [`verify-post-apply.py`](../../scripts/ci/verify-post-apply.py) for its
  exact checks and limits.
- [`security-scan.yml`](../../.github/workflows/security-scan.yml) defines
  repository security scanning. Review its triggers and job conditions before
  relying on a particular scan result.

These files describe configured automation; they do not establish that
external branch protections, GitHub environment reviewers, or other GitHub
settings are enabled. Review workflow logs and current repository settings
through the applicable process. A local configuration check or plan does not
prove deployed cloud posture.

## State, Access, and Security

Normal workload stacks include
[`live/_envcommon/remote-state.hcl`](../_envcommon/remote-state.hcl); that file
derives state configuration and key from shared catalog data and hierarchy.
Use the [live-layer guide](../README.md) for backend bootstrap and migration
procedures. Do not edit remote state manually.

AWS provider configuration is generated by the shared provider layer or, for
two workload leaves, by their stack-specific provider blocks. These blocks
include account allow-lists; the workload account catalog still has placeholder
IDs, so deployment readiness must be checked before any cloud operation. See
[`SECURITY.md`](../../SECURITY.md) for vulnerability reporting. The SCP policy
used by `scp-attachments` is
[`restrict-regions.json`](../../policies/scp/restrict-regions.json).

## Ownership and Support

The [stack ownership inventory](../../inventory/stack-owners.yaml) lists
`@Mahdiar-Farzinfar` as owner for each current workload stack.
[`CODEOWNERS`](../../CODEOWNERS) defines repository path ownership, while
[`CONTRIBUTING.md`](../../CONTRIBUTING.md) and the
[pull-request template](../../.github/PULL_REQUEST_TEMPLATE.md) describe
change submissions. Include affected accounts, regions, stacks, resource
impact, validation evidence, dependencies, and deployment and rollback
considerations where applicable.

## Troubleshooting

- For local tool or platform setup, use the repository's
  [cross-platform setup scripts](../../scripts/cross-platform/) and
  [`verify-env.py`](../../scripts/tools/verify-env.py).
- For state backend prerequisites, migration, or ordering, consult the
  [live-layer guide](../README.md) and
  [`deployment-order.yaml`](../../inventory/deployment-order.yaml). Do not
  attempt state repair from this README.
- For validation, plan, apply safe-skip, drift, or post-apply results, inspect
  the corresponding workflow run and linked script. The apply workflow does
  not currently perform an apply.
- For ownership questions, check
  [`stack-owners.yaml`](../../inventory/stack-owners.yaml); report security
  vulnerabilities according to [`SECURITY.md`](../../SECURITY.md).

## Related Documentation

- [Repository Overview](../../README.md)
- [Live Infrastructure Configuration](../README.md)
- [Deployment Order](../../inventory/deployment-order.yaml)
- [Stack Ownership](../../inventory/stack-owners.yaml)
- [Tool Setup](../../scripts/cross-platform/)
- [Environment Verification](../../scripts/tools/verify-env.py)
- [Contributing](../../CONTRIBUTING.md)
- [Security Policy](../../SECURITY.md)
- [Pull Request Template](../../.github/PULL_REQUEST_TEMPLATE.md)
