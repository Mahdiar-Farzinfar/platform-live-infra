# Organization audit trail for the security account and us-east-1.
#
# The Log Archive account owns the destination bucket and its retention,
# Object Lock, bucket policy, and KMS key. This stack owns the CloudTrail trail
# and its Security-account CloudWatch Logs/KMS resources.

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

dependency "log_archive_bucket" {
  # The destination is owned by the sibling Log Archive account stack.
  config_path = "../../../log-archive/us-east-1/log-archive-bucket"

  enabled = !contains(["init", "validate", "render"], get_terraform_command())

  # Allow configuration-only validation and planning before the Log Archive
  # account has been provisioned. Real outputs are used whenever state exists.
  mock_outputs = {
    bucket_id  = "security-log-archive-us-east-1"
    bucket_arn = "arn:aws:s3:::security-log-archive-us-east-1"
  }
  mock_outputs_allowed_terraform_commands = ["init", "plan", "validate", "render", "output"]
}

locals {
  dependency_placeholder_commands = [
    "init",
    "validate",
    "render",
  ]

  log_archive_bucket_placeholder = "security-log-archive-us-east-1"

  common = read_terragrunt_config(
    "${get_repo_root()}/live/common.hcl"
  )
  common_locals = try(local.common.locals, {})

  module_name = "cloudtrail"
  module_source = try(
    local.common_locals.module_sources[local.module_name],
    null
  )

  # Keep the trail name stable and independent of unresolved account IDs.
  trail_name = "platform-organization-audit"
}

terraform {
  source = local.module_source
}

inputs = {
  name       = local.trail_name
  trail_name = local.trail_name

  # The Log Archive bucket is externally managed. Its bucket policy must
  # explicitly authorize this Security-account trail ARN and the selected
  # CloudTrail prefix before apply; the CloudTrail module does not alter
  # external bucket policies.
  create_s3_bucket = false
  s3_bucket_name = contains(
    local.dependency_placeholder_commands,
    get_terraform_command(),
  ) ? local.log_archive_bucket_placeholder : dependency.log_archive_bucket.outputs.bucket_id
  s3_key_prefix    = "cloudtrail"
  s3_force_destroy = false

  # Keep retention and immutability ownership in the Log Archive bucket stack.
  # The external bucket's Object Lock/COMPLIANCE policy is not overridden here.
  s3_lifecycle_enabled = false

  # Use a Security-account CMK managed by this stack for the trail and its
  # CloudWatch Logs group. The Log Archive CMK remains scoped to the archive
  # account's bucket and is not reused across account boundaries.
  create_kms_key          = true
  kms_key_deletion_window = 30

  enable_cloudwatch_logs         = true
  cloudwatch_logs_retention_days = 365

  # Capture all management events, including global services, from all Regions.
  # The module always enables CloudTrail log-file validation.
  enable_logging                = true
  is_multi_region_trail         = true
  include_global_service_events = true
  event_selectors = [
    {
      read_write_type           = "All"
      include_management_events = true
      data_resources            = []
    }
  ]
  advanced_event_selectors = []
  insight_selectors        = []

  tags = merge(
    {
      Name      = local.trail_name
      Component = "cloudtrail"
    },
    try(include.tagging.locals.tags, {})
  )
}
