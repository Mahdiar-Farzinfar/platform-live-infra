# Management-account GitHub Actions OIDC provider stack.
#
# The module is intentionally configured with no IAM roles until repository-
# owned GitHub subject claims and least-privilege policies are cataloged.

include "region" {
  path   = find_in_parent_folders("region.hcl")
  expose = true
}

include "provider" {
  path = find_in_parent_folders("_envcommon/provider.hcl")
}

include "remote_state" {
  path = find_in_parent_folders("_envcommon/remote-state.hcl")
}

include "tagging" {
  path           = find_in_parent_folders("_envcommon/tagging.hcl")
  expose         = true
  merge_strategy = "deep"
}

locals {
  common = read_terragrunt_config(
    "${get_repo_root()}/live/common.hcl"
  )
  common_locals = try(local.common.locals, {})

  module_source = try(
    local.common_locals.module_sources["github-oidc"],
    null
  )
}

terraform {
  source = local.module_source
}

inputs = {
  # The module default is true; keeping it explicit documents ownership of the
  # account-level provider in this stack without introducing a second provider.
  create_oidc_provider = true

  roles = {
    apply = {
      name        = "github-actions-apply"
      description = "Allows GitHub Actions to apply live infrastructure changes."

      # Exact subject claim for a protected deployment environment.
      subjects = [
        "repo:Mahdiar-Farzinfar/platform-live-infra:environment:production",
      ]

      # Attach the least-privilege policy required for apply.
      managed_policy_arns = [
        "arn:aws:iam::123456789012:policy/github-actions-apply",
      ]

      tags = {
        Purpose = "apply"
      }
    }
  }

  tags = try(include.tagging.locals.tags, {})
}
