# Management-account Service Control Policy stack.
#
# This stack creates one explicitly selected policy without attaching it until
# canonical organization root, OU, or account target IDs are available.

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
    local.common_locals.module_sources["scp"],
    null
  )

  policy_name = "deny-create-iam-user"
  policy_path = "${get_repo_root()}/policies/scp/${local.policy_name}.json"
}

terraform {
  source = local.module_source
}

inputs = {
  name           = local.policy_name
  policy_content = file(local.policy_path)

  # Attachments remain empty until canonical organization targets are added to
  # repository-owned configuration. This prevents implicit root-wide rollout.
  target_ids = []

  tags = try(include.tagging.locals.tags, {})
}
