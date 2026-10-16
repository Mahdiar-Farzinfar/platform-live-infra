# Contributing to platform-live-infra

Thank you for contributing to platform-live-infra.

This repository composes and operates live AWS infrastructure with Terraform and
Terragrunt. It owns account and Region targeting, provider and backend
configuration, dependency ordering, policy attachment, deployment metadata,
and operational verification. Reusable AWS resource implementations are
maintained in the companion platform-iac-modules repository.

This guide defines the production contribution standards for this repository.
When documentation and an enforced repository rule differ, follow the enforced
rule and open a focused documentation correction.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Security Reporting](#security-reporting)
- [Scope and Repository Boundary](#scope-and-repository-boundary)
- [Prerequisites](#prerequisites)
- [Contributor Quick Start](#contributor-quick-start)
- [Command Map](#command-map)
- [Credentials and Environment](#credentials-and-environment)
- [Repository Layout](#repository-layout)
- [Development Workflow](#development-workflow)
- [Adding or Changing a Terragrunt Stack](#adding-or-changing-a-terragrunt-stack)
- [Branching and Commit Conventions](#branching-and-commit-conventions)
- [Pull Request Process](#pull-request-process)
- [Validation and Testing](#validation-and-testing)
- [State and Deployment Safety](#state-and-deployment-safety)
- [Security and Secrets](#security-and-secrets)
- [Documentation Standards](#documentation-standards)
- [Module Version Management](#module-version-management)
- [Release and Change Management](#release-and-change-management)
- [Cross-Platform Development](#cross-platform-development)
- [Troubleshooting](#troubleshooting)
- [Support and Governance](#support-and-governance)
- [Contributor Checklist](#contributor-checklist)

## Code of Conduct

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). Keep
issues, pull requests, reviews, and operational discussions respectful,
specific, and focused on improving the platform.

## Security Reporting

Do not disclose vulnerabilities, credentials, private keys, unredacted state,
or sensitive account information in a public issue or pull request. Follow the
private reporting process in [SECURITY.md](SECURITY.md). Reports should include
sanitized stack, account, Region, commit, reproduction, and impact details.

## Scope and Repository Boundary

This repository is the live composition and operations layer. It owns:

- account, Region, environment, and provider targeting;
- Terragrunt includes, inputs, dependencies, and state keys;
- remote backend configuration and migration procedures;
- module version selection through live/catalogs/module-versions.hcl;
- organization policies under policies/scp/;
- deployment order and stack ownership inventories;
- plan, apply, drift, and post-deployment controls.

The companion platform-iac-modules repository owns reusable Terraform
resources and module interfaces. Do not copy module internals here. If a
capability is missing, open a design issue before adding a new module or an
undocumented input.

## Prerequisites

Install Git, a supported shell, and the repository’s required toolchain.

The supported tools and their configuration are maintained in the following
repository files:

- [tooling/.terraform-version](tooling/.terraform-version)
- [tooling/.terragrunt-version](tooling/.terragrunt-version)
- [tooling/.tool-versions](tooling/.tool-versions)

Use the repository-managed tool versions and configuration rather than
silently upgrading an individual tool while working on a change. If a tool is
missing or its version does not match the repository configuration, install or
activate it using the project’s standard tooling workflow’s standard tooling workflow includes Terraform, Terragrunt, Python, AWS CLI, and the
repository’s configured validation, security, linting, formatting, and
shell-related utilities. The authoritative list and configuration are
maintained in the files above; this document intentionally does not duplicate
specific version numbers.

Applying infrastructure additionally requires approved short-lived AWS
credentials, access to the target account, permission to assume the configured
deployment role, and an initialized backend. Static formatting, linting, and
parsing should not require cloud credentials.

## Contributor Quick Start

Choose one of the following setup paths:

- **Native setup:** install or configure the required tools directly on Linux,
  macOS, or Windows.
- **Dev Container:** use the repository's reproducible containerized
  development environment.

Run the commands below from the repository root unless stated otherwise.

### Native setup

Clone the repository first:

On Linux or macOS:

```bash
git clone https://github.com/Mahdiar-Farzinfar/platform-live-infra.git
cd platform-live-infra
git status --short
```

On Windows PowerShell:

```powershell
git clone https://github.com/Mahdiar-Farzinfar/platform-live-infra.git
Set-Location platform-live-infra
git status --short
```

A fresh checkout should produce no output from `git status --short`.

#### Install or configure the repository toolchain

On Linux or macOS, run the cross-platform setup script:

```bash
./scripts/cross-platform/setup.sh
```

On Windows PowerShell, run:

```powershell
.\scripts\cross-platform\setup.ps1
```

These scripts provide the quickest way to install or configure the tools
required by the repository. Use the repository-managed versions defined in
the `tooling/` directory and run the scripts only from a trusted checkout.

After the setup completes, verify the environment by running the following
command from the repository root on Linux, macOS, or Windows PowerShell:

```bash
task verify-env
```

The `task verify-env` command checks the repository metadata and required tools.
It is read-only; it does not install software or modify credentials.

### Dev Container

As an alternative to installing the toolchain natively, you can use the
repository's reproducible Dev Container environment.

The container configuration is defined by
[.devcontainer/devcontainer.json](.devcontainer/devcontainer.json) and its
Dockerfile.

To pull the prebuilt development container image:

```bash
docker pull ghcr.io/mahdiar-farzinfar/platform-live-infra/devcontainer:latest
```

After pulling the image, open the repository in a Dev Container-compatible
editor and reopen the workspace in the container. Use the container terminal
to run the verification and repository validation commands.

The Dev Container mounts host AWS and Git configuration. Use approved
credentials only, confirm the mounted configuration before running
cloud-backed commands, and never bake credentials, access keys, private keys,
or other sensitive data into the image or repository.

Pulling or opening the Dev Container does not changes.
Do not run ` run `terragrunt apply` manually. The only exception is the approved
bootstrap procedure.

Do not run `terragrunt plan`, `terragrunt destroy`, bootstrap, or state
migration unless the prerequisites, credentials, backend, approvals, and
safety requirements described in this guide have been satisfied.

## Command Map

This repository uses [Task](https://taskfile.dev/) as its canonical task
runner. `Taskfile.yml` is the single source of truth (SoT) for repository
commands, task names, dependencies, and execution behavior.

`Makefile` and `justfile` are convenience wrappers around `Taskfile.yml`.
They do not define an independent command system and must not diverge from the
Task-based workflow. Contributors may use whichever interface is most
convenient:

- `task` for the canonical Task-based interface;
- `just` through the repository's `justfile` wrapper;
- `make` through the repository's `Makefile` wrapper.

When the behavior or availability of a command is unclear, inspect the
`Taskfile.yml` first. If a command is added, renamed, or removed, update the
Taskfile and the corresponding wrappers and documentation in the same change.

### List available commands

To view the available commands, run the command supported by your preferred
interface:

```bash
task --list
just --list
make help
```

The output of `task --list` is authoritative because `Taskfile.yml` is the
repository's single source of truth.

### Environment verification

Verify the local development environment with:

```bash
task verify-env
```

This task is read-only. It checks repository metadata and the required tools;
it does not install software or modify credentials.

### Formatting

Run the repository's formatting checks and formatters with:

```bash
task fmt
```

Review the resulting changes before committing. Do not commit unrelated
formatting changes.

### Pre-commit checks

Run all configured pre-commit hooks against the repository with:

```bash
pre-commit run --all-files
```

Run this command before opening a pull request. If a hook modifies files, review
the changes and rerun the command until it completes successfully.

### CI-equivalent checks

Run the repository's CI-oriented validation locally with:

```bash
task ci
```

This task is intended to provide the local equivalent of the repository's
standard continuous-integration checks. Review the task definition if you need
to understand its exact scope.

### Security checks

Run the complete configured security check suite with:

```bash
task security-all
```

Security findings must not be ignored or broadly suppressed. Handle them
according to the repository's security and exception-management requirements.

### Terragrunt commands

Run Terragrunt commands from the relevant deployable leaf directory. A leaf
directory is a directory containing the applicable `terragrunt.hcl` target.

Direct Terragrunt commands may require initialized backend configuration,
available dependencies, valid provider credentials, and access to the target
AWS account. Do not run cloud-backed operations merely as part of local
formatting or static validation.

In particular, do not run `terragrunt apply` manually except where the approved
bootstrap procedure explicitly permits it. Follow the repository's
[State and Deployment Safety](#state-and-deployment-safety) requirements before
running `terragrunt plan`, `terragrunt destroy`, bootstrap, or state migration.

## Credentials and Environment

Use short-lived federated credentials wherever possible. Never commit access
keys, session tokens, private keys, passwords, state files, plan files, or
variable files containing secrets.

Common environment variables include `AWS_PROFILE`, `AWS_REGION`, and
`AWS_ACCOUNT_ID`. Provide non-secret `TF_VAR_*` values only where explicitly
supported by the relevant script.

Before running commands that access AWS, verify the active identity, target
account, and Region. Do not use production credentials for exploratory
validation.

## Repository Layout

```text
platform-live-infra/
├── live/
│   ├── terragrunt.hcl             # Root configuration
│   ├── common.hcl                 # Shared organization values
│   ├── catalogs/                  # Accounts, Regions, tags, module versions
│   ├── _envcommon/                # Provider, state, and tagging includes
│   ├── bootstrap/                 # Backend creation and state migration
│   ├── foundation/                # Management, log-archive, security accounts
│   └── workloads/                 # Workload account stacks
├── policies/scp/                  # AWS Organizations policies
├── inventory/                     # Deployment DAG and stack ownership
├── scripts/                       # Bootstrap, setup, and tooling helpers
├── tooling/                       # Version and scanner configuration
├── docs/                          # MkDocs source and implementation guidance
├── .devcontainer/                 # Reproducible development environment
├── .github/                       # PR template and repository configuration
├── README.md                      # Architecture and operator overview
├── SECURITY.md                    # Security policy and reporting
└── CONTRIBUTING.md                # Contributor policy
```

Deployable units are leaf directories containing terragrunt.hcl. Parent
account.hcl, region.hcl, catalog, and environment-common files compose
configuration but are not independent deployment targets.

## Development Workflow

1. Read the affected stack, its nearest account and Region configuration, and
   the relevant pinned module documentation.
2. Create a focused branch from main.
3. Make the smallest change that satisfies the requirement.
4. Update deployment and ownership inventories when paths or dependencies change.
5. Run formatting, parsing, validation, and security checks for the changed scope.
6. Review rendered configuration and plans for account, Region, state, IAM, KMS,
   S3, CloudTrail, GuardDuty, and SCP impact.
7. Open a pull request with sanitized evidence and rollback notes.

Do not run `terragrunt apply` manually, except where explicitly permitted by
the approved bootstrap procedure. Deployment must be performed through the
repository's CI/CD workflow from the exact reviewed commit. The workflow must
validate and apply only the approved plan associated with that commit.

## Adding or Changing a Terragrunt Stack

Use the established hierarchy:

```text
live/<layer>/<account>/account.hcl
live/<layer>/<account>/<region>/region.hcl
live/<layer>/<account>/<region>/<stack>/terragrunt.hcl
```

When changing a stack:

- reuse root, account, Region, provider, remote-state, and tagging includes;
- load metadata from catalogs or parent configuration;
- resolve module sources through live/catalogs/module-versions.hcl;
- use only variables and outputs in the pinned module interface;
- declare real dependencies explicitly and avoid cycles;
- preserve deterministic names and state keys;
- use mock dependency outputs only for validation or speculative planning when
  real outputs are not yet available; never allow mocks during apply or use
  a mock-backed plan for deployment;
- update inventory/stack-owners.yaml;
- update inventory/deployment-order.yaml;
- document security, cost, replacement, and rollback impact.

Do not add local Terraform resources to work around a missing module input.
Coordinate a module change in the companion repository and promote its released
version through the live catalog.

## Branching and Commit Conventions

### Branching and merge policy

`main` is the protected integration branch. All changes to `main` must go
through a pull request from a short-lived, focused branch. Direct pushes and
force-pushes to `main` are prohibited. These requirements also apply to
documentation changes, hotfixes, and release changes.

Create working branches from `main` and use descriptive names:

- `feature/<account>-<component>` for account-specific work;
- `feature/<short-description>` for repository-wide work;
- `hotfix/<short-description>` for urgent fixes.

Keep each branch limited to one coherent change. Before merging, ensure that
required reviews and checks are valid for the latest revision. Update the
branch when required by repository rules or integration changes, and rerun
affected checks.

Prefer squash merges unless repository policy requires another strategy.
When squashing, ensure the final commit message follows the conventions below
and retains the required DCO sign-offs.

### Conventional Commits

Write commit messages in English using Conventional Commits:

```text
<type>(<scope>): <short description>
```

Use a type that reflects the change: `feat`, `fix`, `docs`, `style`,
`refactor`, `test`, `chore`, `ci`, `perf`, `build`, or `revert`.

Choose a meaningful scope such as `bootstrap`, `foundation`, `workloads`,
`security`, or `root`. Keep the description concise and explain the reason,
operational impact, and relevant constraints in the commit body when needed.

Mark incompatible changes with `!` before the colon or a `BREAKING CHANGE:`
footer. Describe what becomes incompatible and any required migration or
operator action; the marker alone is not sufficient documentation.

```text
feat(bootstrap)!: change backend state key layout

BREAKING CHANGE: Existing stacks require state migration before using
the new backend layout. Follow the migration procedure included in this change.
```

Commit messages provide structured change history for release management.
Repository versioning, tagging, and release requirements belong in
[Release and Change Management](#release-and-change-management).

### Mandatory DCO sign-off

Every commit must include a Developer Certificate of Origin (DCO) sign-off
with the contributor's name and email:

```text
Signed-off-by: Your Name <your.email@example.com>
```

Add your sign-off with `git commit -s`:

```bash
git commit -s -m "fix(workloads): correct sandbox role trust"
```

For commits created through VS Code's built-in Git interface, automatic
sign-off is enabled in the repository's workspace settings at
`./.vscode/settings.json`. Ensure your Git name and email are configured
correctly, and verify that the resulting commit includes the `Signed-off-by:`
trailer. This setting does not apply to commits created from the terminal;
use `git commit -s` for those commits.

All commits in a pull request must include the required sign-offs. The squash
commit created during merging must also carry the applicable sign-offs;
do not discard other contributors' sign-offs when combining their work.

A DCO sign-off records certification under the DCO. It is not a cryptographic
commit signature and does not replace required reviews or checks.

## Pull Request Process

### Current maintenance and review model

This repository currently follows a single-maintainer model: one person
maintains the repository and performs PR review and approval. Independent
review is therefore not currently guaranteed, including for changes authored
by the maintainer.

All changes must still follow the documented PR process, pass required
checks, and comply with repository protection rules. The single-maintainer
model does not waive validation, security, or change-management requirements.

As additional maintainers, contributors, or reviewers join, review and
approval responsibilities will be delegated to qualified individuals based
on their expertise, assigned responsibilities, and repository permissions.
Contribution alone does not grant approval or merge authority. Independent
review should be used whenever a qualified reviewer is available, especially
for security-sensitive changes.

### Preparing a pull request

Before opening a PR:

- complete [.github/PULL_REQUEST_TEMPLATE.md](.github/PULL_REQUEST_TEMPLATE.md);
- identify affected accounts, Regions, stacks, policies, and modules;
- include validation commands and their results, noting any checks not run
  and the reasons;
- attach only sanitized plan excerpts; do not include credentials, secrets,
  or sensitive state data;
- describe resource replacement risk, state migration requirements, cost
  impact, security implications, and rollback or recovery steps;
- identify any infrastructure or security expertise required for review;
  under the current model, the sole maintainer performs this assessment;
- update documentation and inventories when behavior or ownership changes.

### Review and approval

The maintainer, or qualified reviewers assigned as the project grows, must
verify account targeting, least privilege, trust policies, remote-state
safety, dependency ordering, resource replacement risk, tagging, and
operational readiness.

Security-sensitive changes include SCPs, provider role-assumption settings,
OIDC trust, KMS policies, CloudTrail, GuardDuty, backend settings, and CI
authentication. Document the relevant security assessment and any unresolved
risks in the PR.

For maintainer-authored PRs under the single-maintainer model, record the
self-review, validation results, and merge rationale in the PR. Do not
represent self-review as independent approval or bypass repository protection
rules to merge.

### Changes requiring prior discussion

Open an issue or design discussion before broad refactors, new architecture,
organization-wide guardrail changes, or coordinated module releases.
This requirement also applies under the single-maintainer model so that
design decisions, risks, and implementation plans remain documented.

## Validation and Testing

Run the narrowest checks covering the changed scope.

The following Terragrunt and Terraform tasks operate on the entire repository
by default:

```bash
task fmt:terragrunt:hcl
task validate:terragrunt:hcl
task render:terragrunt
task validate:terraform
```

To scope these checks to a single stack, provide the `TARGET` variable. For
example:

```bash
task fmt:terragrunt:hcl TARGET=live/foundation/security/us-east-1/guardduty
task validate:terragrunt:hcl TARGET=live/foundation/security/us-east-1/guardduty
task render:terragrunt TARGET=live/foundation/security/us-east-1/guardduty
task validate:terraform TARGET=live/foundation/security/us-east-1/guardduty
```

Run Terragrunt plan only after the backend, credentials, dependencies, and
account metadata are ready. Do not run apply or destroy for routine local
validation.

Run repository-wide checks, when the corresponding tools are installed:

```bash
task fmt:terraform
task lint:terraform
task lint:yaml
task lint:markdown
task scan:checkov
task scan:trivy:config
task scan:gitleaks
```

The tasks above correspond to the following repository-wide checks:

- `task fmt:terraform` — `terraform fmt -check -recursive`
- `task lint:terraform` — `tflint --recursive`
- `task lint:yaml` — `yamllint inventory policies`
- `task lint:markdown` — `markdownlint-cli2 "**/*.md"`
- `task scan:checkov` — `checkov -d .`
- `task scan:trivy:config` — `trivy config .`
- `task scan:gitleaks` — `gitleaks detect --no-banner`

Validate SCP policy documents with a JSON parser before opening a policy PR:

```bash
task validate:scp:json
```

This task must validate all SCP JSON documents under `policies/scp`, including:

```bash
python -m json.tool policies/scp/deny-create-iam-user.json > /dev/null
python -m json.tool policies/scp/deny-disable-cloudtrail.json > /dev/null
python -m json.tool policies/scp/restrict-regions.json > /dev/null
```

Findings may be suppressed only through a reviewed exception that includes an
owner, rationale, tracking reference, and expiry date. Do not suppress
material risk.

For bootstrap or cross-platform changes, use safe validation or dry-run modes.
Do not execute bootstrap or state migration against a live backend without an
approved change window and a documented recovery plan.

## State and Deployment Safety

Remote state is configured in `live/_envcommon/remote-state.hcl`. Follow the
commands and instructions in [README.md](README.md) to bootstrap the backend
and migrate state. Backend bootstrap is a special case: create the backend
using local state, then migrate normal stacks to the approved remote backend
with encryption and state locking enabled.

Never edit state manually, commit state or plans, or delete migration backups.
Review resource addresses, for_each keys, imports, and replacement behavior.
Document moved blocks, imports, migration steps, and rollback procedures.

Deployment order is represented in
[inventory/deployment-order.yaml](inventory/deployment-order.yaml). The normal
sequence is backend bootstrap, state migration, management and archive
prerequisites, governance and archive storage, centralized security services,
and workload baselines. Do not rely on lexical directory order.

## Security and Secrets

Follow [SECURITY.md](SECURITY.md):

- use short-lived federated credentials and narrow trust conditions;
- enforce least privilege for IAM, KMS, S3, Organizations, CloudTrail, and
  GuardDuty;
- preserve centralized audit logging and detection;
- review effective SCP policy before attachment;
- block public access by default;
- use approved secret stores or protected CI variables;
- treat state, plans, logs, and provider configuration as sensitive data.

Do not replace unresolved values with plausible fake identifiers. Use explicit
repository placeholders only where genuinely unavailable, keep controls
enabled, and call out replacement requirements in the PR.

## Documentation Standards

Update documentation in the same PR when architecture, deployment order,
state handling, operations, security controls, module versions, or contributor
workflow changes. Keep examples executable and links relative to files that
exist in this repository.

Use [README.md](README.md) for the operator overview and
[docs/index.md](docs/index.md) for the documentation site. The MkDocs
configuration is [mkdocs.yml](mkdocs.yml). If navigation references a page
that does not exist yet, do not claim it is available; correct navigation or
add the page in the same scoped change.

Write contributor-facing material in English. Explain intent, constraints,
security trade-offs, and rollback considerations instead of restating syntax.

## Module Version Management

Module sources and approved refs are centralized in
[live/catalogs/module-versions.hcl](live/catalogs/module-versions.hcl). Use
modules_with_source; do not invent Git refs or use unversioned sources.

When promoting a module version:

1. inspect the companion module README, interface, examples, and security impact;
2. update catalog version and compatibility metadata;
3. verify the source ref and digest policy;
4. test in the sandbox scope first;
5. review replacements, permission changes, and cost;
6. roll out in the approved deployment order.

Implementation changes belong in platform-iac-modules; this repository consumes
reviewed, immutable releases or refs.

## Release and Change Management

This project uses CalVer with constrained SemVer-style compatibility rules
for infrastructure changes. Releases represent a validated platform baseline,
including module versions and operational changes, rather than a standalone
software package.

Release automation is managed by
[.github/workflows/release.yml](.github/workflows/release.yml). The workflow
generates or updates `CHANGELOG.md`. Changes to `CHANGELOG.md` must pass
through the required PR review and validation process and be included in the
commit selected for release.

### Versioning and tags

Use immutable tags in the format `vYYYY.MM.PATCH`:

- `v2026.09.0`: the initial platform release for September 2026.
- `v2026.09.1`: a backward-compatible correction released in the same month,
  such as a workflow fix, policy correction, or configuration adjustment that
  preserves the consumer contract.
- `v2026.10.0`: the initial platform release for October 2026, which may
  include significant changes to stacks, state, providers, policies, or
  module interfaces.

`YYYY.MM` identifies the actual release year and month; it is not a SemVer
major/minor pair. Reset `PATCH` to zero for the first release of each month
and increment it for subsequent compatible corrections. Do not advance the
calendar component solely to signal a breaking change.

Reserve patch releases for low-risk, backward-compatible corrections.
Assess compatibility by impact, not by file type: policy and configuration
changes can break consumers or disrupt operations.

Use `feat!`, another Conventional Commit type with `!`, or a
`BREAKING CHANGE:` footer to identify incompatible changes. Such changes
require an explicit compatibility review, migration instructions, and a
planned release rather than an automatic patch release. Schedule them for
a subsequent monthly baseline where practical.

Release tags must be signed and protected against unauthorized creation,
modification, and deletion. Verify the tag signature before publishing.
Never move or reuse an existing release tag, and do not use floating tags
such as `latest` or `stable`.

### Release workflow and changelog

Create releases only from signed, protected tags pointing to reviewed
commits merged into `main`. Before publishing, the release workflow must
confirm successful validation, security scans, Terraform/Terragrunt plans,
and applicable smoke tests for the selected commit.

Checks requiring deployed infrastructure must run in an approved test
environment. Production deployment and post-deployment verification remain
subject to the deployment approval process.

Every release must include a `CHANGELOG.md` generated from Conventional
Commits and reviewed for accuracy and operational impact. Commit scopes may
include `foundation`, `workload`, `policy`, `module`, `workflow`, `docs`,
and `security`.

The `CHANGELOG.md` must correspond to the tagged commit. Generate, review,
and merge the updated changelog before creating the immutable release tag.
Do not modify release content after tagging.

### Release artifacts and evidence

In addition to the source archive, include a release manifest and sanitized
validation evidence recording:

- the release tag and full commit SHA;
- the Terraform, Terragrunt, provider, and module versions used;
- the stacks changed since the previous release;
- plan summaries, including resource replacements and destructive changes;
- security check results and any approved exceptions;
- the deployment order;
- approval status and references to the relevant review records.

Do not publish credentials, secrets, state files, raw plan files, or
unsanitized logs as release artifacts. Record pending deployment approvals
as pending; release publication does not imply deployment authorization.

### Deployment, promotion, and recovery

A release tag identifies a traceable platform version and provides a
reference for rollback planning. Publishing a release must not automatically
run `apply` across all environments.

After publication, the workflow should promote the same release artifact
and commit through GitHub Environments, with separate approval gates for
`foundation` and `workloads`. Follow the approved deployment order and
record deployment results and approvals for each environment.

Generate and review environment-specific plans using the released commit.
Do not reuse a Terraform plan across environments. Re-plan and obtain the
required approval if changes invalidate the previously reviewed plan.

Document changes to guardrails, state layout, account targeting, provider
assessments, and rollback or recovery instructions.

A previous tag does not guarantee that an infrastructure change can be
reversed safely. Document state migration requirements, backup and recovery
steps, irreversible operations, and any cases requiring a forward fix
instead of rollback.

## Cross-Platform Development

Bootstrap and setup workflows provide PowerShell, POSIX shell, and Python
variants. Keep their behavior equivalent. Use UTF-8, LF endings,
repository-relative paths, and forward slashes in HCL/YAML metadata.

When changing a cross-platform script, test the Python implementation and the
affected wrapper. Prefer dry-run or validation modes and never apply
infrastructure merely to test portability.

## Troubleshooting

### Environment verification fails

Compare installed versions with tooling/ and use the Dev Container if a native
tool is missing. The verifier is read-only and does not repair the host.

### Terragrunt cannot initialize or validate

Confirm the working directory, include paths, module ref, Terraform and
Terragrunt versions, backend configuration, and credentials. If an account or
foundation dependency does not exist, static HCL checks may pass while
provider-backed validation remains unavailable.

### A plan proposes unexpected replacement or policy detachment

Stop. Review state addresses, dependency outputs, account and Region context,
module changes, and policy content. Do not approve or apply until the change
and rollback path are understood.

### State migration is blocked

Do not delete local state or retry blindly. Confirm the backend stack is
complete, the remote bucket and lock table are reachable, no other migration is
running, and a recovery backup exists. Follow the bootstrap script's lock and
validation guidance.

### A documented command does not exist

Treat the mismatch as documentation drift. Verify the actual files, then open a
focused correction rather than adding an undocumented alias.

## Support and Governance

Use GitHub issues for reproducible bugs, feature requests, and architecture
questions. Include the affected stack, sanitized output, tool versions, account
and Region scope, and the smallest reproduction available.

For standard support and communication with contributors, use the **Discussions**
section in the repository.

The repository maintainer has final authority over architecture, releases,
security exceptions, and breaking changes. Security concerns must follow
[SECURITY.md](SECURITY.md), not a public issue. Protected paths and ownership
are defined in [CODEOWNERS](CODEOWNERS).

## Contributor Checklist

Before requesting review:

- [ ] The change is narrowly scoped and follows the live hierarchy.
- [ ] Account, Region, provider, backend, and module-version context is explicit.
- [ ] Includes, dependencies, inputs, and outputs were verified.
- [ ] Formatting, parsing, validation, and applicable security scans pass.
- [ ] No secrets, credentials, state, plans, or fake identifiers were added.
- [ ] Security and operational impact was reviewed.
- [ ] Deployment order and stack ownership were updated when needed.
- [ ] Documentation and examples were updated for behavior changes.
- [ ] Replacement, migration, rollback, cost, and operational impact are documented.
- [ ] The PR template is complete and evidence is sanitized.
- [ ] Every commit follows Conventional Commits and includes DCO sign-off.

Thank you for helping keep the live platform secure, reviewable, and
operationally predictable.
