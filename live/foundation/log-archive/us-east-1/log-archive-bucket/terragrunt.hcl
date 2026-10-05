# Centralized log archive bucket for the log-archive account and us-east-1.
#
# The bucket consumes the customer-managed KMS key from the sibling KMS stack.
# Bucket policy, ownership controls, public access blocking, TLS enforcement,
# versioning, and lifecycle resources are owned by the reusable module.

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

dependency "kms" {
  config_path = "../kms"

  enabled = !contains(["init", "validate", "render"], get_terraform_command())

  # Permit configuration-only validation and planning before the KMS stack has
  # been applied. The real key_arn is used whenever dependency state exists.
  mock_outputs = {
    key_arn = "arn:aws:kms:us-east-1:000000000000:key/00000000-0000-0000-0000-000000000000"
  }
  mock_outputs_allowed_terraform_commands = ["init", "plan", "validate", "render", "output"]
}

locals {
  dependency_placeholder_commands = [
    "init",
    "validate",
    "render",
  ]

  kms_key_placeholder = "arn:aws:kms:us-east-1:000000000000:key/00000000-0000-0000-0000-000000000000"

  common = read_terragrunt_config(
    "${get_repo_root()}/live/common.hcl"
  )
  common_locals = try(local.common.locals, {})

  module_name = "log-archive-bucket"
  module_source = try(
    local.common_locals.module_sources[local.module_name],
    null
  )

  # Keep the name deterministic and independent of unresolved account IDs.
  # The account/region hierarchy already provides unique Terraform state
  # identity, while this stable name avoids renaming the archive bucket when
  # the catalog's TBD account ID is replaced.
  bucket_name = "security-log-archive-us-east-1"
}

terraform {
  source = local.module_source
}

inputs = {
  bucket_name = local.bucket_name

  # Use the sibling KMS key for SSE-KMS; the module enables the S3 Bucket Key
  # automatically whenever kms_key_arn is non-null.
  kms_key_arn = contains(
    local.dependency_placeholder_commands,
    get_terraform_command(),
  ) ? local.kms_key_placeholder : dependency.kms.outputs.key_arn

  force_destroy = false

  # Preserve archived logs indefinitely while tiering older objects to lower
  # cost storage classes. Noncurrent versions remain within the seven-year
  # compliance retention period represented in the account catalog.
  lifecycle_prefix                   = ""
  transition_to_ia_days              = 30
  transition_to_glacier_days         = 90
  transition_to_deep_archive_days    = 365
  expiration_days                    = null
  noncurrent_version_expiration_days = 2555

  # Object Lock is an account-level log-archive requirement and must be enabled
  # at bucket creation. COMPLIANCE mode prevents bypass, including by root.
  object_lock_enabled        = true
  object_lock_mode           = "COMPLIANCE"
  object_lock_retention_days = 2555

  # No separate access-log destination is cataloged for this account.
  access_log_bucket = null

  # These are the documented AWS service principals used for centralized
  # CloudTrail and delivery-service writes. The module scopes writes to the
  # owning account and denies all non-TLS requests.
  log_delivery_service_principals = [
    "cloudtrail.amazonaws.com",
    "delivery.logs.amazonaws.com",
  ]

  tags = merge(
    {
      Name      = local.bucket_name
      Component = "log-archive-bucket"
    },
    try(include.tagging.locals.tags, {})
  )
}
