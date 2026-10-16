# Changelog

## [v2026.10.0] - 2026-10-16

<!-- release-source: 3d5fb4d9c98ff12210f19d92537a1923e29ae5c9; release-kind: repository -->

Compatibility: baseline. Review the actual diff and operational impact.

### Features

- feat(inventory): add deployment order and stack ownership metadata (`c47f7b09e43c`)
- feat(bootstrap): add remote state bootstrap and migration scripts (`3ab6a913f1e3`)
- feat(policies): add SCP guardrails for IAM, CloudTrail, and regions (`d06a178820dc`)
- feat(cross-platform): add setup shims for tool installation (`1e76b42e97f1`)
- feat(terragrunt): add root live catalog and stack composition (`da7b63be6c54`)
- feat(catalogs): add centralized live infrastructure catalogs (`420e7022fe0f`)
- feat(terragrunt): add shared environment composition (`532428f3b8af`)
- feat(bootstrap): add backend bootstrap stack with pinned providers (`5233b92ff16e`)
- feat(management): add GitHub OIDC and SCP foundation stacks (`d53eb1d7b79f`)
- feat(log-archive): add encrypted centralized logging stacks (`48ee0f28971f`)
- feat(workloads): initialize sandbox account composition (`ef5fb5a7c12f`)
- feat(sandbox): add workload security and access stacks (`eeadeeaadf45`)
- feat(devcontainer): add development container image workflow (#8) (`b19f22096a6d`)
- feat(tooling): add native installers for development tools (#10) (`8b73e268ee8f`)

### Fixes

- fix(release): scope remote ref lookup to tags (#7) (`743f3b68198d`)
- fix(devcontainer): copy tool versions to workspace root (`f4b477c40319`)
- fix(release): handle PRs without review records (#13) (`cabfb37e0cdf`) (PR #13)

### Documentation

- docs(release): prepare image/devcontainer/v0.1.0 changelog (#12) (`13932720af4c`) (PR #12)
- docs(mkdocs): add infrastructure documentation site (#14) (`393f361168fc`) (PR #14)

### Security Changes

- feat(security): add CloudTrail and GuardDuty foundation stacks (`7a320a7720d6`)

### Operational Changes

- chore(repo): add gitattributes for repository defaults (`e1b4908fa11c`)
- chore(repo): add editor and ignore defaults (#1) (`c2ae2341e65a`)
- chore(tooling): add versioned development tool configuration (#2) (`968dde1510f0`)
- chore(build): add task runner wrappers and pre-commit config (#3) (`19961debd8cb`)
- chore(devex): add VS Code workspace configuration (#4) (`9e5b3ccab9f4`)
- chore(ci): add CI bootstrap scripts for workflow prep (#5) (`bb23e225b971`)
- test(smoke): add security baseline smoke test coverage (`30451f8a6035`)
- ci(workflows): add GitHub Actions workflow suite (`90719d758a13`)
- chore(ci): refine workflow tooling and documentation dependencies (`fd4de05513a7`)
- chore(ci): move actionlint into validation workflow (`cb7c1f279530`)
- chore(ci): install shfmt in validation workflow (`d9799e8b9cc6`)
- chore(repo): add governance and project documentation (#15) (`3d5fb4d9c98f`) (PR #15)

## [image/devcontainer/v0.1.0] - 2026-10-12

<!-- release-source: f4b477c4031962f0bf741fa2f01de97b4e609542; release-kind: image -->

Compatibility: image-initial. Review the actual diff and operational impact.

### Dev Container Image Changes

- chore(tooling): add versioned development tool configuration (#2) (`968dde1510f0`)
- chore(ci): add CI bootstrap scripts for workflow prep (#5) (`bb23e225b971`)
- feat(cross-platform): add setup shims for tool installation (`1e76b42e97f1`)
- feat(devcontainer): add development container image workflow (#8) (`b19f22096a6d`)
- feat(tooling): add native installers for development tools (#10) (`8b73e268ee8f`)
- fix(devcontainer): copy tool versions to workspace root (`f4b477c40319`)
