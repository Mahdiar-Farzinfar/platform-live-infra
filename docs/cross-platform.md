# Cross-Platform Development

## Purpose

This guide describes how to prepare and validate a local development environment for this Terraform and Terragrunt live-configuration repository. It is for contributors, platform engineers, CI maintainers, and operators who need to understand the limits of local and CI workflows.

Local setup provides tools for repository work; it does not authorize or define production deployment. Follow the repository's [security policy](../SECURITY.md), [live infrastructure guidance](../live/README.md), and applicable [bootstrap](bootstrap.md), [deployment-order](deployment-order.md), and [state-management](state-management.md)
procedures for infrastructure operations. This guide treats checked-in implementations and workflow definitions as evidence, and distinguishes declared behavior from behavior actually exercised by CI.

## Scope and Support Matrix

`Verified` means a repository workflow or test directly exercises the listed behavior. `Partially verified` means some relevant configuration or checks exist but end-to-end platform parity is not established. `Not verified` means this checkout contains no direct evidence of support.

| Environment or platform | Status | Evidence | Shell or runtime | Notes |
| --- | --- | --- | --- | --- |
| Windows | Verified for setup and selected checks | [`cross-platform-test.yml`](../.github/workflows/cross-platform-test.yml) runs on `windows-latest`; invokes the PowerShell setup wrapper, Go installer tests, SCP JSON validation, and YAML lint | PowerShell (`pwsh` in CI); Python and Go | The workflow successfully validates the Windows tool-installation path through `install-tools-windows.go` and confirms that the tools required by the repository's Taskfile targets are included in the Windows toolchain. It does not independently execute every Taskfile target on Windows, so target-level behavior beyond tool availability remains outside the scope of this workflow. |
| Linux | Verified for setup and selected checks | Same workflow runs on `ubuntu-latest`; invokes Bash setup, Go installer tests, SCP JSON validation, and YAML lint | Bash; Python and Go | Full validation and security workflows run on `ubuntu-24.04`. |
| macOS | Verified for setup and selected checks | Same workflow runs on `macos-latest` with the Bash setup wrapper and selected checks | Bash; Python and Go | Not all repository tasks or cloud operations are tested on macOS. |
| Devcontainer | Partially verified | [`Dockerfile`](../.devcontainer/Dockerfile), [`devcontainer.json`](../.devcontainer/devcontainer.json), and [`devcontainer-image.yml`](../.github/workflows/devcontainer-image.yml) define a Debian-based image and Linux amd64/arm64 build | Linux container; Bash | The workflow builds and publishes a multi-architecture Dev Container image for Linux amd64 and arm64 platforms. |
| GitHub Actions | Verified for specific workflows | Cross-platform workflow has Ubuntu, macOS, and Windows jobs; other validation/security workflows use Ubuntu 24.04 | Workflow-specific Bash or PowerShell | Workflow definitions do not establish branch protection, required checks, or full local/CI parity. The documented workflows should be evaluated through their configured jobs and repository-level CI settings. |
| Git Bash, WSL, other POSIX distributions | Not verified as host environments | No dedicated host matrix or explicit support commitment found | Varies | The POSIX helper accepts Linux/macOS routing, but this alone does not prove complete support for other environments or distributions. |

These statuses apply to the checks named in the evidence column, not to every tool, task, architecture, or infrastructure operation. The setup implementations explicitly handle Windows amd64/arm64 and POSIX Linux/macOS amd64/arm64; the CI host matrix does not separately test each architecture.

## Platform-Specific Entry Points

The setup scripts install or verify local development tools. They do not configure cloud infrastructure. Python and Go must be available early enough for the wrappers and installer to run; wrappers may attempt to provision Python when no suitable interpreter is found.

| Entry point | Intended platform | Purpose and inputs | Side effects and risk | Verification and limits |
| --- | --- | --- | --- | --- |
| [`setup.ps1`](../scripts/cross-platform/setup.ps1) | Windows | PowerShell wrapper; discovers Python and reads the canonical and mirror tool-version files before invoking `setup.py` with Windows context. Accepts the Python CLI's remaining arguments. | Local environment setup/tool installation. May install Python via available `mise`, `pyenv`, `winget`, or Chocolatey; may require network or package-manager privileges. Then invokes the Go tool installer, which installs tools and updates user/process PATH. No repository or infrastructure mutation is intended by the inspected code. | Checks Python against the pinned minimum, then delegates shared validation and Go setup. Windows installer handles amd64 and arm64; unsupported architectures fail. Reruns recheck tools and can update Scoop metadata or reinstall/repair tools. |
| [`setup.sh`](../scripts/cross-platform/setup.sh) | Linux/macOS POSIX hosts | Bash wrapper; reads Python pin, searches installed Python, then tries available `mise`, `asdf`, or `pyenv`, followed by platform package-manager paths. Delegates to `setup.py`. | Local environment setup/tool installation. Network access is needed for downloads/package installs. Linux apt/dnf installation can require root or sudo; Homebrew is used on macOS. | Requires Bash; CI invokes it as `bash ./scripts/cross-platform/setup.sh`, so executable-bit behavior is not relied on there. Only Linux/macOS are routed by the installer. Reruns recheck and reconcile tool installations. |
| [`setup.py`](../scripts/cross-platform/setup.py) | Windows, Linux, macOS (or explicit supported alias) | Shared Python implementation validates `tooling/.tool-versions`, `go.mod`, and the version mirror; detects platform; invokes the appropriate Go installer using `go run`; then verifies Go. The script resolves repository root from its own location unless `--root` is supplied. | Runs a local tool installer, which can download and install tools; not read-only. Does not itself mutate Terraform state or infrastructure. | Python 3 is required. `--dry-run` validates and reports intended Go-installer action, but does not guarantee wrappers can proceed if Python itself is absent; Windows/POSIX wrappers describe their own dry-run behavior. Exit codes distinguish validation, installer, unsupported platform, post-install, interruption, and unexpected failures. |
| [`verify-env.py`](../scripts/tools/verify-env.py), via `task verify-env` | Windows/Linux/macOS as recognized by its platform detection | Read-only repository/tool verifier; checks version-file consistency and installed tools/versions. | Read-only; does not install tools, change PATH, or contact infrastructure. | Missing tools or version mismatches are reported as failures. It has a quiet/JSON output mode; use the documented Task target for the supported repo entry point. |
| [`install-tools-windows.go`](../scripts/tools/install-tools-windows.go) | Windows amd64/arm64 | Go installer selected by `setup.py`; reads version sources and installs/verifies pinned tools using Scoop and selected release downloads. | Local installation, network requests, persistent user PATH updates, and temporary files. Scoop must already be installed; the installer reports that it will not bootstrap Scoop. | Uses bounded subprocess/network timeouts and reports install/verification failures. No infrastructure mutation. |
| [`install-tools-posix.go`](../scripts/tools/install-tools-posix.go) | Linux/macOS amd64/arm64 | Go installer selected by `setup.py`; uses available package-manager or tool-manager paths for pinned utilities. | Local installation and downloads; some Linux system package routes require root/sudo. | Explicitly rejects unsupported architectures and platform routes. No infrastructure mutation. |

The wrappers validate their version inputs and report failures; they are not a guarantee that every package is available for every distribution or architecture. Do not run a normal setup command if you only intend to inspect behavior: `--dry-run` is available, but it still requires the relevant wrapper runtime and does not test successful
installation.

## Toolchain and Version Consistency

The repository has multiple version declarations with different roles:

| Source | Role and enforcement |
| --- | --- |
| [`tooling/.tool-versions`](../tooling/.tool-versions) | Canonical inventory consumed by the setup/install/verifier code and read by selected CI steps. It declares Terraform, Terragrunt, Go, Python, Node.js, and utility/linter/task-runner versions. A declaration alone does not install a tool. |
| [`tooling/cross-platform/asdf-tool-versions`](../tooling/cross-platform/asdf-tool-versions) | Full mirror of the canonical inventory. Setup and verification code compare inventory and versions and fail on divergence. |
| [`tooling/.terraform-version`](../tooling/.terraform-version) and [`tooling/.terragrunt-version`](../tooling/.terragrunt-version) | Dedicated Terraform and Terragrunt pins consumed by CI setup actions and repository setup logic. Keep aligned with the corresponding canonical entries. |
| [`go.mod`](../go.mod) | Go module language/toolchain contract. Setup logic checks its Go directive against the concrete `golang` pin; devcontainer build validation also checks these pins. |

The current canonical pins are:

| Group | Tools and pinned versions |
| --- | --- |
| Infrastructure | Terraform `1.15.6`; Terragrunt `1.1.1` |
| Runtimes | Go `1.26.0`; Python `3.12.4`; Node.js `24.18.0` |
| Infrastructure tooling | AWS CLI `2.22.17`; Docker CLI `29.6.1`; TFLint `0.56.0`; Trivy `0.72.0`; Checkov `3.3.8` |
| Lint and validation | yamllint `1.37.1`; ShellCheck `0.11.0`; shfmt `3.13.1`; markdownlint-cli2 `0.17.2`; Gitleaks `8.30.1`; Actionlint `1.7.7`; golangci-lint `2.13.1` |
| Task runners and utilities | Task `3.39.2`; Just `1.36.0`; Make `4.4.1`; pre-commit `4.0.1`; jq `1.7.1`; yq `4.44.6` |

CI explicitly installs selected pinned versions: cross-platform tests extract Python, Task, and yamllint pins and Go from `go.mod`; validation extracts Python, Node.js, Task, yamllint, Markdownlint, Terraform, and Terragrunt pins; other workflows install their own subsets. This is workflow-specific enforcement, not a guarantee every local tool
invocation automatically selects the pin. The Dev Container Dockerfile additionally pins its base image digest and build-time asdf and Go versions.

`Taskfile.yml` is the implemented task catalog. `justfile` and `Makefile` are convenience wrappers that delegate to Task; they do not provide independent task logic. `make` and `just` are not prerequisites when invoking `task` directly. The repository provides a `pre-commit` task and corresponding configuration for running the project's pre-commit checks.

## Shell and Command Conventions

- Use PowerShell for the Windows setup wrapper: `.\scripts\cross-platform\setup.ps1`.
- Use Bash for the POSIX setup wrapper: `bash ./scripts/cross-platform/setup.sh`.
- Task targets run a mix of native commands and POSIX shell blocks. The Windows CI job deliberately runs only selected tasks that are compatible with its setup; do not infer that all targets in `Taskfile.yml` run unchanged in PowerShell.
- `justfile` sets `powershell.exe` as its Windows shell and forwards individual wrapper targets to `task`; Make delegates to Task. Task handles Task variable syntax and command arguments as defined in the Taskfile.
- The repository normalizes text line endings to LF and forces CRLF for PowerShell and batch scripts through [`.gitattributes`](../.gitattributes). [`.editorconfig`](../.editorconfig) sets UTF-8, final newlines, whitespace, and per-language indentation. CI explicitly calls the Bash script rather than relying on its executable bit.
- Scripts use OS-specific path handling in Python/Go/PowerShell. Quote paths containing spaces when invoking commands; do not translate shell syntax mechanically between Bash and PowerShell.

## Repository Setup Procedure

Run from the checked-out repository. The wrappers derive the root from their own file location; Task commands should be run at the repository root because several tasks use repository-relative paths.

1. Confirm the intended checkout and repository root using your normal Git workflow. No repository-specific clone command is defined here.
2. Identify the host OS and shell. Use PowerShell on Windows and Bash on Linux/macOS for the corresponding setup wrapper.
3. Review the canonical pins and Go contract in [`tooling/.tool-versions`](../tooling/.tool-versions), [`go.mod`](../go.mod), and their mirror before installation.
4. For an inspection-only run, invoke the platform wrapper with `--dry-run`. This validates inputs and avoids tool installation, but cannot verify a successful setup and may not work if the needed Python runtime is missing.
5. To install or reconcile local tools, run the platform wrapper without `--dry-run`:

   ```powershell
   .\scripts\cross-platform\setup.ps1
   ```

   ```bash
   bash ./scripts/cross-platform/setup.sh
   ```

   These commands can install Python and other pinned development tools, access the network, and on Linux may invoke privileged package installation. Review the relevant wrapper and installer before approving operating-system prompts. Failures are returned as nonzero exit codes with diagnostics; correct the reported prerequisite or pin mismatch and rerun.
6. To use the published Dev Container image, ensure that Docker is installed and running, then pull the public image from GHCR:

   ```bash
   docker pull ghcr.io/mahdiar-farzinfar/platform-live-infra/devcontainer:latest
   ```

   The image is publicly available, so GHCR authentication is not required for this pull operation. The image is built and published by [`devcontainer-image.yml`](../.github/workflows/devcontainer-image.yml).
7. Once prerequisites are installed, run `task verify-env` for read-only version/inventory checks. A passing result verifies only the checks implemented by the script.
8. Run safe repository checks as needed. `task validate` is the Taskfile's non-cloud validation target, but it initializes Terraform validation with `-backend=false` and may download provider/module dependencies. `task fmt` modifies files unless `CHECK=true`; prefer `CHECK=true` for a non-mutating formatting check.

Setup changes local tools, files, or PATH according to platform implementation. It is distinct from repository source changes and from any state or infrastructure operation.

## Common Workflows

Commands below are defined by [`Taskfile.yml`](../Taskfile.yml). Do not add Task arguments or variable values without checking that file and the underlying script.

| Workflow | Repository entry point | Platform notes | Risk | Expected evidence |
| --- | --- | --- | --- | --- |
| Verify tool pins and installed tools | `task verify-env` | Python runtime and pinned tools required | Read-only local inspection | Per-tool/inventory result and exit status |
| Check Terraform/Terragrunt formatting | `task fmt CHECK=true` | Includes a Taskfile POSIX shell block for Terragrunt; host-shell compatibility is not fully matrix-tested | Read-only when `CHECK=true`; otherwise edits files | Check/diff output or nonzero failure |
| Validate configuration | `task validate` | Uses Terraform/Terragrunt, Python, yamllint, and Markdownlint; Terraform validation initializes with backend disabled and can download dependencies | Local validation; no apply/state mutation defined by task | Validation/linter output and exit status |
| Validate SCP JSON | `task validate:scp:json` | Python standard library; exercised in cross-platform CI | Read-only | “SCP JSON validation passed” or failure |
| YAML lint | `task lint:yaml` | Python yamllint; exercised in cross-platform CI | Read-only | yamllint findings or success |
| Markdown lint | `task lint:markdown` | Markdownlint-cli2; CI runs on Ubuntu | Read-only | Markdownlint findings or success |
| Rendered security baseline check | `task verify:security-baseline` | Requires Terragrunt and local render ability; used by validation/security workflows | Local render and file inspection; no AWS API calls in the verifier path | Named PASS/FAIL/SKIP checks; not evidence of deployed posture |
| Go installer tests | `go test ./scripts/tools` | Cross-platform CI executes on its OS matrix | Local test/build activity; no infrastructure mutation | Go test output and exit status |
| Plan, drift, bootstrap, state migration, apply, cleanup | Not setup-validation workflows | Cloud identity/state access or local destructive effects may be involved | Excluded from routine cross-platform validation | Follow the operational documentation and authorized workflow only |

Other lint and scan tasks are available, but some have external download behavior (for example, Checkov downloads external modules by default locally; the security workflow disables those downloads). Review task implementation before running broad scans. Shell lint auto-fixes unless `CHECK=true`.

## CI and Local Parity

[`cross-platform-test.yml`](../.github/workflows/cross-platform-test.yml) tests setup and selected checks on `ubuntu-latest`, `macos-latest`, and `windows-latest`. It configures Python, Go, and Task; installs yamllint; runs the native platform setup wrapper, Go installer tests, SCP JSON validation, and YAML lint. It does not run the full
Taskfile validation/security suite, the Python smoke regression tests, or cloud operations.

[`validate.yml`](../.github/workflows/validate.yml) and [`security-scan.yml`](../.github/workflows/security-scan.yml) run on Ubuntu 24.04 for pull requests, pushes to `main`, and manual dispatch (security scan also has a schedule). Validation checks formatting, SCP JSON, YAML, Markdown, and a local rendered baseline. Security scan adds configured
Checkov, Trivy, Gitleaks, and Actionlint checks. These workflows do not prove AWS deployed posture.

Planning and drift workflows separate pull-request metadata work from trusted-main cloud planning and use OIDC for cloud-aware jobs. They are operator/CI workflows, not cross-platform developer checks. The apply workflow is manually dispatched but its Taskfile path deliberately skips resource creation; it is not evidence of an active apply
deployment. Post-apply checks report live checks as pending. Workflow definitions and triggers do not establish branch protection or required status checks.

## Devcontainer Workflow

The devcontainer is implemented as a Debian 13 based image with a digest-pinned base image. Its Dockerfile installs system prerequisites, asdf, Go, and the repository's POSIX installer-managed toolchain; it explicitly supports Linux amd64 and arm64 build targets. `devcontainer.json` sets `/workspaces/<repository>` as the workspace, uses the
non-root `vscode` user, configures Bash, VS Code extensions, and a post-create tool-version check. It bind-mounts host SSH and Git configuration read-only and host AWS configuration without a read-only flag. Treat mounted credentials as sensitive and use only authorized local identity configuration.

Docker and a Dev Containers-compatible editor/runtime are needed to build and use this environment. The container requests 2 CPUs, 4 GB memory, and 32 GB storage, and sets `SYS_PTRACE` plus unconfined seccomp in `runArgs`;
assess these host requirements against local policy. The [`devcontainer-image.yml`](../.github/workflows/devcontainer-image.yml) workflow builds the Dev Container image for Linux amd64 and arm64 and publishes it to GitHub Container Registry (GHCR).
The repository and its container image are publicly available, so users can pull and use the image without GHCR authentication. The published image is available at `ghcr.io/mahdiar-farzinfar/platform-live-infra/devcontainer:latest`.

## Environment Variables and Credentials

The setup implementation recognizes the following platform-selection overrides; ordinary setup wrapper usage does not require setting them.

| Variable | Purpose | Required when | Sensitive | Source |
| --- | --- | --- | --- | --- |
| `CROSS_PLATFORM_PLATFORM` | Override platform detection for setup/verifier code | Optional override only | No | `setup.py`, `verify-env.py` |
| `SETUP_PLATFORM` | Alternate platform-detection override | Optional override only | No | `setup.py`, `verify-env.py` |
| `BOOTSTRAP_WRAPPER_OS` | Alternate wrapper platform context | Optional override only | No | `setup.py`, `verify-env.py` |
| `AWS_DRIFT_ROLE_ARN` | Reviewed repository variable used by trusted-main planning/drift workflow to assume its planning role | Cloud planning workflow configuration | Sensitive operational identifier; do not reproduce its value in docs/logs | [`plan.yml`](../.github/workflows/plan.yml), [`drift-detection.yml`](../.github/workflows/drift-detection.yml) |

The local environment verifier does not validate AWS credentials or identity. Cloud-aware CI obtains credentials through its OIDC workflow configuration; local credentials are handled by the AWS tooling and repository provider configuration, not by cross-platform setup. Do not print credential values or commit them. For account, Region, identity,
and state expectations, use the [live guide](../live/README.md) and [state-management guide](state-management.md). Treat local output, plans, and CI artifacts as potentially sensitive.

## File-System, Git, and Line-Ending Considerations

`.editorconfig` sets UTF-8, LF, final newline, and whitespace defaults with language-specific indentation. `.gitattributes` explicitly normalizes repository text to LF and PowerShell/batch files to CRLF; it also marks binary formats and compiled executables appropriately. These settings guide editors and Git checkout/commit normalization; they do
not establish full compatibility with case-insensitive filesystems.

`.gitignore` excludes local credentials, environment files, provider/Terragrunt caches, Terraform state and plan files, Python caches, and common generated outputs while allowing provider lockfiles to remain trackable. `.terraformignore` controls files excluded from Terraform packaging and is not a general-purpose Git ignore file. Do not commit
state, plans, credentials, caches, or generated secret material. CI explicitly invokes the POSIX setup script through Bash, so local executable-bit behavior should not be assumed.

## Cross-Platform Failure Handling

| Symptom | Likely cause | Safe diagnostic | Next action |
| --- | --- | --- | --- |
| Setup reports malformed, missing, or divergent pins | Verified setup validation failure in canonical/mirror files or Go module contract | Inspect the relevant lines in `tooling/.tool-versions`, its mirror, and `go.mod` | Correct the source files together through normal review; do not bypass validation. |
| Python is missing or below the required version | Verified wrapper prerequisite; wrapper could not resolve a suitable interpreter or installation route | Check `python`, `python3`, or the Windows Python launcher version and wrapper diagnostics | Install through a supported manager/package path described in the wrapper, then rerun. |
| Go installer cannot start or Go post-check fails | Go missing, timeout, installer error, PATH resolution, or version mismatch | Run `go version`; preserve sanitized setup error and exit status | Resolve runtime/version/install issue; setup validates Go against repository pins. |
| Package manager, network, permissions, or architecture error | Possible host limitation; Linux package installation may require root/sudo, Windows needs preinstalled Scoop, and installers make network requests | Record OS, architecture, manager availability, and error text without credentials | Use the platform-specific supported route or consult repository maintainers through the contribution process; do not weaken host controls. |
| A Task target fails with shell syntax or command lookup errors | Possible host shell mismatch or missing task dependency; not all Taskfile shell blocks are Windows portable | Check the target's `cmds` in `Taskfile.yml` and confirm shell/tool availability | Use documented platform wrapper or a CI-tested target; report the precise target and sanitized failure. |
| Validation/lint reports a formatting or content failure | Repository check detected configuration or documentation mismatch | Use the named file/check output; `task fmt CHECK=true` checks formatting without writing | Correct the source and rerun the relevant read-only check. |
| Cloud operation reports identity, account, Region, or state failure | Cloud workflow/local operation context mismatch, not a local setup verification failure | Stop; inspect authorized workflow summary and approved target metadata without exposing identifiers | Follow security and state procedures; do not retry with broader credentials. |

## Security and Operational Guardrails

The repository ignores common credential, state, and plan artifacts, and the security guidance requires protected operational workflows. The following additional operator practices are general best practices; their presence here does not mean they are technically enforced by this document:

- Do not place credentials or tokens in scripts, shell history, source control, or documentation.
- Do not commit state files, plan files, generated credentials, or sensitive CI artifacts.
- Do not disable validation, security scanning, policy checks, CI/CD, code review, IAM, SCPs, or state locking to address platform differences.
- Do not run infrastructure-mutating commands to test local setup. Use least-privilege identities and verify account and Region before authorized infrastructure operations.
- Treat local output and CI artifacts as potentially sensitive, keep tool versions aligned across platforms, and document platform-specific deviations in the pull request.
- Follow repository deployment and state procedures; local setup does not authorize `apply`, `destroy`, state migration, or state mutation.

## Maintenance and Change Management

Update this guide when setup scripts, supported platform matrices, tool-version sources, Task targets, shell assumptions, devcontainer configuration, workflow runner matrices, environment variables, validation commands, or line-ending policies change. Check the behavior in source and CI rather than copying claims from this document. Follow
[`CONTRIBUTING.md`](../CONTRIBUTING.md), [`CODEOWNERS`](../CODEOWNERS), and the [pull request template](../.github/PULL_REQUEST_TEMPLATE.md) for contribution and review routing; this guide does not create additional approval requirements or support commitments.

## Related Documentation and Source Files

- [Repository overview](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/README.md), [contribution guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/CONTRIBUTING.md), and [security policy](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/SECURITY.md)
- [Bootstrap](bootstrap.md), [deployment order](deployment-order.md), [state management](state-management.md), [live repository guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/live/README.md), and [tests guide](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tests/README.md)
- [Taskfile](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Taskfile.yml), [Makefile](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/Makefile), and [justfile](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/justfile)
- [Setup wrappers and shared setup](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/cross-platform/setup.ps1),
[`setup.sh`](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/cross-platform/setup.sh), [`setup.py`](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/cross-platform/setup.py), [environment verifier](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/scripts/tools/verify-env.py), and [tool installers](https://github.com/Mahdiar-Farzinfar/platform-live-infra/tree/main/scripts/tools/)
- [Tool-version declarations](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tooling/.tool-versions), [Terraform pin](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tooling/.terraform-version),
[Terragrunt pin](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tooling/.terragrunt-version), and [cross-platform version mirror](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/tooling/cross-platform/asdf-tool-versions)
- [Devcontainer definition](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.devcontainer/devcontainer.json),
[Dockerfile](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.devcontainer/Dockerfile), [cross-platform workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/cross-platform-test.yml),
[validation workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/validate.yml), [security workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/security-scan.yml), and [devcontainer image workflow](https://github.com/Mahdiar-Farzinfar/platform-live-infra/blob/main/.github/workflows/devcontainer-image.yml)
