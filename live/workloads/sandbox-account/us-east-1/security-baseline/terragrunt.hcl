# Sandbox workload-account security baseline for us-east-1.
#
# This stack owns the account-local GuardDuty detector and protection features.
# Organization-wide GuardDuty administration is owned by the Security account;
# CloudTrail and SCP ownership remain in their dedicated foundation/sibling
# stacks to avoid duplicate resources and unclear control ownership.

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

  module_name = "guardduty"
  module_source = try(
    local.common_locals.module_sources[local.module_name],
    null
  )

  account_context = try(include.region.locals.account_context, {})
  guardduty_enabled = (
    try(local.account_context.guardduty_enabled, false)
    && try(include.region.locals.enabled_for_account, false)
  )
}

terraform {
  source = local.module_source
}

inputs = {
  # The account catalog is the source of truth for whether this workload
  # participates in the platform GuardDuty baseline. The regional guard keeps
  # an accidentally copied stack from enabling a detector outside an approved
  # account Region.
  enabled                      = local.guardduty_enabled
  finding_publishing_frequency = "FIFTEEN_MINUTES"

  # Explicitly manage the module's supported protection planes so feature
  # coverage is visible in plans and does not depend on module-default drift.
  detector_features = {
    S3_DATA_EVENTS = {
      enabled = true
    }
    EKS_AUDIT_LOGS = {
      enabled = true
    }
    EBS_MALWARE_PROTECTION = {
      enabled = true
    }
    RDS_LOGIN_EVENTS = {
      enabled = true
    }
    LAMBDA_NETWORK_LOGS = {
      enabled = true
    }
    RUNTIME_MONITORING = {
      enabled = true
      additional_configuration = {
        EC2_AGENT_MANAGEMENT         = true
        ECS_FARGATE_AGENT_MANAGEMENT = true
        EKS_ADDON_MANAGEMENT         = true
      }
    }
  }

  # Delegated-administrator registration and organization-wide auto-enable
  # configuration are performed by the Security-account GuardDuty stack. This
  # workload stack must not attempt management-account Organizations calls.
  organization_admin = {
    delegate_admin           = false
    manage_org_configuration = false
    auto_enable              = "NEW"
  }
  organization_features = {}

  # Findings export requires caller-owned bucket/KMS policies and is not
  # configured until an approved destination is provisioned by its owner.
  publishing_destination = null

  # No external feeds or filters are cataloged for the sandbox baseline yet;
  # leaving these collections empty avoids inventing unmanaged security data.
  ipsets            = {}
  threat_intel_sets = {}
  filters           = {}

  tags = merge(
    {
      Name      = "sandbox-account-security-baseline-us-east-1"
      Component = "security-baseline"
    },
    try(include.tagging.locals.tags, {})
  )
}
