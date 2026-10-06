# Sandbox workload-account context for descendant region and component stacks.
#
# This file is intentionally resource-free. It owns account metadata only;
# provider, backend, tagging, dependencies, and module resources remain in the
# shared _envcommon layers and regional/leaf stacks.

locals {
  # The account catalog uses "sandbox", while the live hierarchy and account
  # tag catalog use "sandbox-account". Keep both identities explicit so
  # metadata and account-specific tags resolve without duplicating either
  # catalog entry.
  _root = read_terragrunt_config(find_in_parent_folders("terragrunt.hcl"))

  catalog_account_key = "sandbox"
  account_key         = "sandbox-account" # checkov:skip=CKV_SECRET_6:Not a secret – Terragrunt account-name identifier

  accounts = try(local._root.locals.accounts, {})
  account  = try(local.accounts[local.catalog_account_key], {})

  account_id          = try(local.account.account_id, null)
  account_name        = try(local.account.account_name, local.catalog_account_key)
  account_type        = try(local.account.account_type, null)
  environment         = try(local.account.environment, null)
  organizational_unit = try(local.account.organizational_unit, null)
  criticality         = try(local.account.criticality, null)
  primary_region      = try(local.account.primary_region, null)
  enabled_regions     = try(local.account.enabled_regions, [])

  # Expose workload security and sandbox-governance settings for descendant
  # baseline, guardrail, and test-role stacks without creating resources here.
  cloudtrail_enabled    = try(local.account.cloudtrail_enabled, false)
  guardduty_enabled     = try(local.account.guardduty_enabled, false)
  securityhub_enabled   = try(local.account.securityhub_enabled, false)
  config_enabled        = try(local.account.config_enabled, false)
  auto_shutdown_enabled = try(local.account.auto_shutdown_enabled, false)
  max_instance_types    = try(local.account.max_instance_types, [])
  monthly_budget_usd    = try(local.account.monthly_budget_usd, null)
  budget_alert_emails   = try(local.account.budget_alert_emails, [])

  # Preserve the complete catalog record for consumers that need ownership,
  # compliance, access-control, cost, or operational metadata.
  account_context = {
    key                   = local.account_key
    catalog_account_key   = local.catalog_account_key
    account_id            = local.account_id
    account_name          = local.account_name
    account_type          = local.account_type
    environment           = local.environment
    organizational_unit   = local.organizational_unit
    criticality           = local.criticality
    primary_region        = local.primary_region
    enabled_regions       = local.enabled_regions
    cloudtrail_enabled    = local.cloudtrail_enabled
    guardduty_enabled     = local.guardduty_enabled
    securityhub_enabled   = local.securityhub_enabled
    config_enabled        = local.config_enabled
    auto_shutdown_enabled = local.auto_shutdown_enabled
    max_instance_types    = local.max_instance_types
    monthly_budget_usd    = local.monthly_budget_usd
    budget_alert_emails   = local.budget_alert_emails
    raw                   = local.account
  }
}
