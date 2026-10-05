# Log-archive account KMS key for us-east-1.
#
# The key is owned by this account and consumed by the regional log-archive
# bucket stack. Cross-account service access is intentionally deferred until
# approved principals and delivery policy requirements are cataloged.

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

  module_name = "kms"
  module_source = try(
    local.common_locals.module_sources[local.module_name],
    null
  )
}

terraform {
  source = local.module_source
}

inputs = {
  # Stable identity for the customer-managed key used by centralized logging.
  description = "Customer-managed KMS key for the log-archive account and us-east-1 audit storage."
  aliases     = ["alias/log-archive"]

  # Symmetric encryption with annual automatic rotation and the module's
  # maximum deletion grace period protect retained audit data from accidental
  # key loss.
  key_usage                          = "ENCRYPT_DECRYPT"
  key_spec                           = "SYMMETRIC_DEFAULT"
  is_enabled                         = true
  enable_key_rotation                = true
  rotation_period_in_days            = null
  multi_region                       = false
  deletion_window_in_days            = 30
  bypass_policy_lockout_safety_check = false

  # The module always includes current-account root recovery access. Additional
  # principals remain empty until repository-owned IAM role ARNs are approved.
  key_administrators        = []
  key_users                 = []
  key_service_users         = []
  source_policy_documents   = []
  override_policy_documents = []
  grants                    = {}

  tags = merge(
    {
      Name      = "log-archive-kms"
      Component = "kms"
    },
    try(include.tagging.locals.tags, {})
  )
}
