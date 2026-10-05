# Security-account context for descendant region and component stacks.
#
# This file is intentionally resource-free. It owns account metadata only;
# provider, backend, tagging, and service-specific resources remain in the
# shared _envcommon layers and regional/leaf stacks.

locals {
  # Load the root contract without include nesting. Terragrunt allows only one
  # include level, and region/leaf stacks already include files that consume this
  # account context.
  root        = read_terragrunt_config(find_in_parent_folders("terragrunt.hcl"))
  root_locals = try(local.root.locals, {})

  # The key is the canonical identifier used by live/catalogs/accounts.hcl.
  # Keep the lookup explicit so the catalog's intentional account-ID
  # placeholder remains visible until the AWS account is provisioned.
  catalog_account_key = "security"
  account_key         = local.catalog_account_key

  accounts = try(local.root_locals.accounts, {})
  account  = try(local.accounts[local.catalog_account_key], {})

  account_id          = try(local.account.account_id, null)
  account_name        = try(local.account.account_name, local.catalog_account_key)
  account_type        = try(local.account.account_type, null)
  environment         = try(local.account.environment, null)
  organizational_unit = try(local.account.organizational_unit, null)
  criticality         = try(local.account.criticality, null)
  primary_region      = try(local.account.primary_region, null)
  enabled_regions     = try(local.account.enabled_regions, [])

  # Security-account service ownership flags are exposed as metadata for
  # regional and component stacks; resources themselves are owned by those
  # stacks and are not created from this account context file.
  cloudtrail_enabled        = try(local.account.cloudtrail_enabled, false)
  guardduty_enabled         = try(local.account.guardduty_enabled, false)
  securityhub_enabled       = try(local.account.securityhub_enabled, false)
  config_enabled            = try(local.account.config_enabled, false)
  guardduty_administrator   = try(local.account.guardduty_administrator, false)
  securityhub_administrator = try(local.account.securityhub_administrator, false)
  macie_enabled             = try(local.account.macie_enabled, false)
  access_analyzer_enabled   = try(local.account.access_analyzer_enabled, false)

  # Preserve the complete catalog record for consumers that need ownership,
  # compliance, access-control, or operational metadata.
  account_context = {
    key                       = local.account_key
    catalog_account_key       = local.catalog_account_key
    account_id                = local.account_id
    account_name              = local.account_name
    account_type              = local.account_type
    environment               = local.environment
    organizational_unit       = local.organizational_unit
    criticality               = local.criticality
    primary_region            = local.primary_region
    enabled_regions           = local.enabled_regions
    cloudtrail_enabled        = local.cloudtrail_enabled
    guardduty_enabled         = local.guardduty_enabled
    securityhub_enabled       = local.securityhub_enabled
    config_enabled            = local.config_enabled
    guardduty_administrator   = local.guardduty_administrator
    securityhub_administrator = local.securityhub_administrator
    macie_enabled             = local.macie_enabled
    access_analyzer_enabled   = local.access_analyzer_enabled
    raw                       = local.account
  }
}
