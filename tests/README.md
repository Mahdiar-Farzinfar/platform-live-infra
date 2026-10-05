# Infrastructure Testing

## Testing overview

The `tests/` directory contains a configuration-focused smoke verifier and focused Python regression tests for its decision logic. These checks complement repository validation, linters, security scans, advisory plans, drift scans, and post-apply workflow checks. Each provides different evidence; none alone proves that deployed AWS resources have the intended posture.

The repository keeps these activities distinct:

- **Local validation and static analysis** check formatting, HCL/Terraform configuration, policy JSON, YAML, Markdown, and configured lint/security rules. The `validate` task describes its checks as non-cloud validation.
- **Planning** evaluates proposed infrastructure changes. Plans can need cloud identity and remote-state access; repository plans are advisory and do not apply changes.
- **Smoke verification** renders selected Terragrunt configurations locally and checks configured inputs and policy documents. It does not query AWS.
- **Post-apply verification** checks a selected inventory scope and configured baseline; its live checks are reported as pending.
- **Drift detection** runs read-only plans against remote-state stacks to identify drift or operational errors.
- **Apply** is a separate infrastructure-changing operation. The checked-in apply workflow currently invokes the apply task with resource creation disabled.

These controls do not provide unit or integration coverage for the reusable Terraform modules, prove effective AWS Organizations policy attachment, or establish live resource posture. Module implementations and their tests belong to the companion module repository.

## Testing philosophy and safety model

Prefer deterministic checks against repository configuration and read-only inspection where possible. Keep validation, planning, applying, and post-deployment verification separate. A passing render-based check is evidence about rendered configuration only. Report failures with enough context to investigate, while avoiding sensitive values.

- Do not run infrastructure-mutating commands to validate documentation or test code.
- Do not bypass repository workflows, review controls, or authorization boundaries.
- Do not use personal or excessive cloud credentials. Confirm the intended account and Region before cloud-aware operations.
- Do not commit credentials, state files, or generated plans that may contain sensitive data. Redact account IDs, ARNs, tokens, and similar values from reports when appropriate.
- Treat a failed check as a reason to investigate; do not weaken assertions or bypass controls to obtain a pass.
- Tests must not silently mutate infrastructure. Review the implementation and task definition before running a check whose effects are unclear.

## Test repository layout

```text
tests/
├── README.md
└── smoke/
    ├── security-baseline-checklist.md
    └── verify-security-baseline.py
```

The `tests/` directory currently contains only smoke-test assets. No separate unit, integration, acceptance, or end-to-end test suites are defined under `tests/`. Documentation for the security baseline verification is provided in `security-baseline-checklist.md`, and its executable implementation is located in `verify-security-baseline.py`.

## Test categories

| Category | Purpose | Source of truth | Execution context | Mutating? |
| --- | --- | --- | --- | --- |
| Security-baseline smoke check | Check rendered GuardDuty, CloudTrail, archive, KMS, and SCP configuration | [`smoke/verify-security-baseline.py`](smoke/verify-security-baseline.py), invoked by `verify:security-baseline` in [`../Taskfile.yml`](../Taskfile.yml) | Local Terragrunt renders and local JSON reads | No AWS API calls or infrastructure writes in the implemented task path |
| Repository validation and static analysis | Check formatting, configuration, policy JSON, YAML, Markdown, and configured lint rules | [`../Taskfile.yml`](../Taskfile.yml), [`../tooling/`](../tooling/) | Local task runner and CI | Validation/lint tasks are non-mutating except format tasks without `CHECK=true`; scanners inspect repository content |
| Advisory planning | Evaluate infrastructure configuration and proposed changes | [`../scripts/ci/plan.py`](../scripts/ci/plan.py), `plan` task, and [`../.github/workflows/plan.yml`](../.github/workflows/plan.yml) | Local or trusted-main CI; cloud planning identity is required for cloud plans | No apply operation; planning accesses state and cloud APIs as configured |
| Post-apply configuration check | Validate selected stack inventory and configured baseline; report live checks pending | [`../scripts/ci/verify-post-apply.py`](../scripts/ci/verify-post-apply.py), `verify:post-apply` task, and [`../.github/workflows/post-apply-verify.yml`](../.github/workflows/post-apply-verify.yml) | Manual workflow or task invocation | The inspected script delegates to the configuration smoke task; it does not establish live posture |
| Drift detection | Run read-only plans over remote-state stacks and classify drift/errors | [`../scripts/ci/drift-ci.py`](../scripts/ci/drift-ci.py), `drift` task, and [`../.github/workflows/drift-detection.yml`](../.github/workflows/drift-detection.yml) | Scheduled or manual trusted-main workflow with a read-only planning identity | Read-only planning; no apply |
| Security and policy scans | Scan IaC, dependencies, secrets, workflows, and policy/configuration inputs | Security tasks and [`../.github/workflows/security-scan.yml`](../.github/workflows/security-scan.yml) | Local tasks or CI | Scanning only; external-module downloads may occur for Checkov when enabled by its task default |

## Implemented smoke tests

### `smoke/verify-security-baseline.py`

The verifier checks three SCP JSON documents for valid deny-only document structure and selected expected actions or Region rules. It invokes `terragrunt render --json --no-auto-init` for five hard-coded stack configuration paths, then checks selected GuardDuty, CloudTrail, archive-bucket, and KMS inputs. The CloudTrail check compares its destination with the rendered archive bucket input.

The expected inputs are the repository's `live/` and `policies/scp/` files plus an available Terragrunt executable. The task supplies the repository root, executable name, and timeout; `JSON=true` requests JSON output. No AWS credentials or AWS API calls are used by this verifier. Rendered values can contain configuration data, so do not add raw render output to logs or reports.

The verifier prints named `PASS`, `FAIL`, or `SKIP` checks, or a JSON report.
Exit codes are 0 when evaluated configuration checks pass, 1 for configuration
failures, 2 for invalid CLI/repository input, 3 when Terragrunt is unavailable
or cannot run, and 130 when interrupted. Tool/render problems can also appear
in the check list. A zero exit code explicitly does **not** establish deployed
AWS posture. Live posture, CloudTrail log-file validation, cross-account archive
readiness, and SCP attachment/effective-policy checks are skipped or outside
this check's scope.

Run it through the repository-defined task from the repository root:

```sh
task verify:security-baseline
```

This task uses local renders and is non-mutating. It can fail if Terragrunt is unavailable, a render fails, required files are missing, or configuration assertions fail. Inspect the named check and referenced configuration; do not infer live health from this result.

## Running tests and validation

Run commands from the repository root. The Taskfile is the source of truth; `justfile` and `Makefile` delegate to it.

| Command | What it does | Context and access | Effects and output |
| --- | --- | --- | --- |
| `task verify-env` | Checks repository metadata and pinned development tools | Local; requires the configured tools to be installed | Read-only; reports environment/tool checks |
| `task verify:security-baseline` | Runs the smoke verifier described above | Local Terragrunt renders; no AWS credentials | Read-only; text output by default; set Task variable `JSON=true` for JSON |
| `task validate` | Runs Terraform validation, Terragrunt HCL formatting checks, SCP JSON validation, YAML lint, and Markdown lint | Local; toolchain required; validation task is described as non-cloud | Read-only checks; failures return nonzero through Task |
| `task fmt:terraform CHECK=true` | Checks Terraform formatting without rewriting files | Local; Terraform required | Read-only check with diff output |
| `task fmt:terragrunt:hcl CHECK=true` | Checks Terragrunt HCL formatting without rewriting files | Local; Terragrunt required | Read-only check |
| `task lint:terraform`, `task lint:yaml`, `task lint:markdown`, `task lint:actions` | Run configured TFLint, yamllint, Markdownlint, or Actionlint | Local; corresponding tool required | Read-only scans; findings cause task failure |
| `task scan:checkov`, `task scan:trivy:config`, `task scan:trivy:fs`, `task scan:gitleaks` | Run configured IaC/policy, configuration, dependency, and secret scans | Local; scanner tools required; Checkov external module downloads default to enabled | Scans do not apply infrastructure; Checkov may download external modules |

`task validate` is the documented safe local validation entry point. The
broader `task ci` also depends on formatting and security tasks. Formatting
tasks can modify files unless `CHECK=true`, and Checkov may download external
modules. Review task definitions before running broader tasks. Do not run
`apply`, bootstrap, state-migration, or cleanup tasks as a test. Plans and drift
scans require separate target, identity, and state-access review; they are not
part of `tests/` smoke testing.

The verifier has no separate invocation contract beyond the Taskfile task. Do not assume the Python regression suite is included in `task validate` or CI.

## CI/CD integration

Workflow definitions establish the following behavior; they do not by themselves prove branch protection or merge requirements.

| Workflow | Trigger and relevant behavior | Credentials, mutation, and evidence |
| --- | --- | --- |
| [`validate.yml`](../.github/workflows/validate.yml) | Pull requests, pushes to `main`, and manual dispatch. Checks formatting, SCP JSON, YAML, Markdown, and the configured local security baseline. | No AWS posture check; baseline uses local renders. Job failure is visible in Actions. |
| [`security-scan.yml`](../.github/workflows/security-scan.yml) | Pull requests, pushes to `main`, scheduled runs, and manual dispatch. Validates SCP JSON, runs the local-render baseline task, then Checkov, Trivy, Gitleaks, and Actionlint. | Repository scanning; no apply. Scanner output is in workflow logs. |
| [`docs.yml`](../.github/workflows/docs.yml) | Pull requests, pushes to `main`, and manual dispatch. Builds and validates the MkDocs documentation site using the pinned Python version from `tooling/.tool-versions`, then uploads and deploys the Pages artifact on `main`. | Documentation build is read-only and uses locked dependencies; deployment happens only on `main` and not for pull requests. See workflow logs and the generated GitHub Pages deployment status. |
| [`cross-platform-test.yml`](../.github/workflows/cross-platform-test.yml) | Pull requests, pushes to `main`, and manual dispatch. Runs platform setup checks, Go installer tests, and SCP JSON/YAML validation on its OS matrix. | No AWS credentials are configured in the workflow. It does not run the Python smoke regression suite. |
| [`plan.yml`](../.github/workflows/plan.yml) | Pull requests, pushes to `main`, and manual dispatch. Metadata validation is separate from read-only plans, which run only for non-PR events on trusted `main`. | Cloud-plan job uses GitHub OIDC and a reviewed planning identity. Plans are advisory; no apply occurs. See workflow logs and sanitized results. |
| [`drift-detection.yml`](../.github/workflows/drift-detection.yml) | Scheduled and manual runs. Scans remote-state stacks on trusted `main`. | Uses GitHub OIDC with a read-only planning role; read-only plans classify drift and operational errors. See workflow logs/summary. |
| [`post-apply-verify.yml`](../.github/workflows/post-apply-verify.yml) | Manual dispatch after an operator-selected deployment context; validates selected inventory scope and configured baseline. | The workflow does not establish deployed AWS posture; live checks remain pending. See its generated summary and logs. |
| [`apply.yml`](../.github/workflows/apply.yml) | Manual dispatch; verifies the reviewed `main` revision and runs the apply task in the production environment. | The workflow intentionally does not enable AWS resource creation. It is a safe-skip path, not evidence of a functioning apply deployment. |

## Test data, configuration, and secrets

The verifier reads repository policy JSON and rendered inputs from five
configured stack files. Its tests construct temporary policy documents and
mock Terragrunt execution for selected cases. The inspected verifier does not
read required environment variables or credentials. The post-apply, plan, and
drift workflows have separate identity and inventory requirements described
in their scripts and workflow definitions.

Never hard-code secrets or credentials in tests, fixtures, or docs. Do not commit Terraform state, sensitive plan files, or unredacted account identifiers, ARNs, or tokens. Avoid logging secret values, use least-privilege identities for cloud-aware operations, and do not place production credentials in local test configuration. No test-specific secret-management mechanism is defined here.

## Adding or updating tests

1. Read the [repository overview](../README.md), [contributing guide](../CONTRIBUTING.md), and this guide.
2. Choose whether the change belongs in a local configuration check, a regression test, or an operational verification mechanism.
3. Confirm expected behavior against the authoritative configuration, inventory, script, or workflow.
4. Write deterministic assertions with clear failure context and no sensitive output.
5. Keep checks narrowly scoped and safe by default; do not make a smoke test silently mutate infrastructure.
6. Avoid credentials and hard-coded environment identifiers. Use mocks or temporary inputs for local decision-logic tests where appropriate.
7. Reuse existing repository tools and task conventions; do not imply that a new test is CI-wired until a workflow actually runs it.
8. Update this guide when behavior, inputs, safety boundaries, or supported invocation changes.
9. Run verified local validation commands such as `task validate` and the specific smoke task when relevant.
10. Submit a pull request with rationale, scope, risk, and sanitized validation evidence using the [pull request template](../.github/PULL_REQUEST_TEMPLATE.md).
11. Allow configured CI and repository review processes to evaluate the change; do not claim branch protection or required checks unless separately verified.

Add a new smoke check only after identifying the configuration source and the assertion it can support. State whether it needs cloud access, define its failure output and exit behavior, and document its actual task or workflow integration. Do not assume a testing framework or add an undocumented command to contributor guidance.

## Failure analysis and troubleshooting

| Failure | Investigation |
| --- | --- |
| Missing or mismatched tools | Review pinned versions in [`../tooling/`](../tooling/) and the `verify-env` task output; setup details are in [`../CONTRIBUTING.md`](../CONTRIBUTING.md). |
| HCL/Terraform validation or render failure | Inspect the named stack configuration and Task/workflow logs. A render error is not evidence of an AWS posture failure. |
| Smoke assertion or policy JSON failure | Use the failing check name to locate the relevant `live/` input or `policies/scp/` document; confirm the expected behavior before changing assertions. |
| Security/lint scan failure | Review the scanner output and its repository configuration under `tooling/`; do not suppress findings without the documented review process. |
| Missing cloud identity, wrong target, or state access failure | Stop and verify the intended account, Region, inventory scope, and authorized workflow identity. See [`../live/README.md`](../live/README.md) and the relevant workflow logs. Do not retry with broader credentials. |
| Plan, drift, or post-apply check failure | Inspect the workflow summary and logs and the corresponding `scripts/ci/` implementation. Drift exit codes distinguish clean (0), drift (1), and operational error (2); post-apply output can mark live checks pending. |
| CI failure | Open the failed job and step in Actions, then compare its trigger, environment, and command with the checked-in workflow. A workflow result alone does not establish merge protection. |

Do not disable checks, weaken assertions, delete state, or make manual infrastructure changes as troubleshooting shortcuts. Follow the repository's approved operational procedures for any cloud-side action.

## Ownership and support

Use [`../CODEOWNERS`](../CODEOWNERS) and the [pull request template](../.github/PULL_REQUEST_TEMPLATE.md)
to identify review routing and provide test evidence. The
[`../inventory/stack-owners.yaml`](../inventory/stack-owners.yaml) maps
deployable stacks to configured owners; it is infrastructure ownership
metadata, not a general support or response-time commitment. See the
[contributing guide](../CONTRIBUTING.md) for contribution expectations.

## Related documentation

- [Repository overview](../README.md)
- [Contributing guide](../CONTRIBUTING.md)
- [Security policy](../SECURITY.md)
- [Live infrastructure guide](../live/README.md)
- [Documentation index](../docs/index.md)
- [Taskfile](../Taskfile.yml)
- [Stack ownership inventory](../inventory/stack-owners.yaml)
- [Deployment order inventory](../inventory/deployment-order.yaml)
