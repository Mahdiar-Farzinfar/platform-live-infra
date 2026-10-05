# Management-account context for descendant region and component stacks.
#
# This file is intentionally resource-free. It owns account metadata only;
# provider, backend, and tag generation remain in the shared _envcommon layers.

locals {
  # The key is the canonical identifier used by live/catalogs/accounts.hcl.
  # Keep the catalog lookup explicit so unresolved account IDs remain visible
  # as the catalog's intentional placeholder rather than using ambient AWS
  # credentials or caller-account discovery.
  _root = read_terragrunt_config(find_in_parent_folders("terragrunt.hcl"))

  catalog_account_key = "management"
  account_key         = local.catalog_account_key

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

  # Preserve the complete catalog record for consumers that need account-level
  # governance, ownership, compliance, or operational metadata.
  account_context = {
    key                 = local.account_key
    catalog_account_key = local.catalog_account_key
    account_id          = local.account_id
    account_name        = local.account_name
    account_type        = local.account_type
    environment         = local.environment
    organizational_unit = local.organizational_unit
    criticality         = local.criticality
    primary_region      = local.primary_region
    enabled_regions     = local.enabled_regions
    raw                 = local.account
  }
}
