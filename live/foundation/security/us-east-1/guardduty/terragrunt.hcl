# GuardDuty delegated-administrator configuration for the security account and
# us-east-1.
#
# This stack owns the regional detector, protection features, and organization
# auto-enable configuration. Delegated-administrator registration remains a
# separate management-account operation and must complete before this stack.

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

  # Account-level ownership flags are authoritative for this regional stack.
  guardduty_enabled       = include.region.locals.account_context.guardduty_enabled
  delegated_administrator = include.region.locals.account_context.guardduty_administrator
}

terraform {
  source = local.module_source
}

inputs = {
  enabled                      = local.guardduty_enabled
  finding_publishing_frequency = "FIFTEEN_MINUTES"

  # Explicitly manage all protection planes supported by the module. Runtime
  # agent management keeps coverage enabled for EC2, ECS/Fargate, and EKS.
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

  # Registration of the Security account as delegated administrator must be
  # performed from the Management account. This stack runs in the delegated
  # administrator account and owns organization-wide enrollment/configuration.
  organization_admin = {
    delegate_admin           = false
    manage_org_configuration = local.delegated_administrator
    auto_enable              = "ALL"
  }

  organization_features = {
    S3_DATA_EVENTS         = "ALL"
    EKS_AUDIT_LOGS         = "ALL"
    EBS_MALWARE_PROTECTION = "ALL"
    RDS_LOGIN_EVENTS       = "ALL"
    LAMBDA_NETWORK_LOGS    = "ALL"
    RUNTIME_MONITORING     = "ALL"
  }

  # Findings export is intentionally not configured until a caller-owned S3
  # bucket and KMS key with GuardDuty-specific resource policies exist. The
  # module does not create or modify those external policies.

  tags = merge(
    {
      Name      = "security-guardduty-us-east-1"
      Component = "guardduty"
    },
    try(include.tagging.locals.tags, {})
  )
}
