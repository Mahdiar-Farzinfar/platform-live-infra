# Shared Terragrunt configuration for the live infrastructure tree.
#
# This file intentionally contains orchestration metadata and catalog
# projections only. Environment-, account-, region-, and component-specific
# behavior belongs in the consuming stack's terragrunt.hcl.

locals {
  # Resolve catalogs from the repository root so this file remains usable from
  # future live/foundation and live/workloads descendants.
  repository_root = get_repo_root()
  live_root       = "${local.repository_root}/live"
  catalog_root    = "${local.live_root}/catalogs"

  accounts_catalog = try(
    read_terragrunt_config("${local.catalog_root}/accounts.hcl"),
    {}
  )
  regions_catalog = try(
    read_terragrunt_config("${local.catalog_root}/regions.hcl"),
    {}
  )
  tags_catalog = try(
    read_terragrunt_config("${local.catalog_root}/tags.hcl"),
    {}
  )
  module_versions_catalog = try(
    read_terragrunt_config("${local.catalog_root}/module-versions.hcl"),
    {}
  )

  # Raw catalog exports. Keeping these available makes the shared layer useful
  # for stacks that need attributes not represented by the normalized views.
  accounts_catalog_locals        = try(local.accounts_catalog.locals, {})
  regions_catalog_locals         = try(local.regions_catalog.locals, {})
  tags_catalog_locals            = try(local.tags_catalog.locals, {})
  module_versions_catalog_locals = try(local.module_versions_catalog.locals, {})

  accounts = try(local.accounts_catalog_locals.accounts, {})
  regions  = try(local.regions_catalog_locals.regions, {})

  # Stable organization metadata shared by all stacks.
  organization = {
    name               = try(local.tags_catalog_locals.common_tags.Organization, null)
    repository         = try(local.tags_catalog_locals.common_tags.Repository, null)
    management_account = try(local.accounts.management, null)
    primary_region     = try(local.regions_catalog_locals.primary_region, null)
  }

  # Region projections are safe for an empty or partially populated catalog.
  enabled_regions = try(
    local.regions_catalog_locals.enabled_regions,
    {
      for name, config in local.regions :
      name => config
      if try(config.enabled, false)
    }
  )
  enabled_region_names = sort(keys(local.enabled_regions))
  primary_region = try(
    local.regions_catalog_locals.primary_region,
    try(one([
      for name, config in local.regions :
      name
      if try(config.primary, false) && try(config.enabled, false)
    ]), null)
  )

  # Account projections preserve catalog values such as null account IDs.
  # Consumers can use active_accounts when an actual AWS account ID is needed.
  account_ids = {
    for name, account in local.accounts :
    name => try(account.account_id, null)
  }
  account_primary_regions = {
    for name, account in local.accounts :
    name => try(account.primary_region, local.primary_region)
  }
  foundation_account_keys = sort([
    for name, account in local.accounts :
    name if try(account.environment, null) == "foundation"
  ])
  workload_account_keys = sort([
    for name, account in local.accounts :
    name if try(account.account_type, null) == "workload"
  ])
  active_accounts = {
    for name, account_id in local.account_ids :
    name => account_id
    if account_id != null && can(regex("^[0-9]{12}$", tostring(account_id)))
  }
  active_account_ids = sort(values(local.active_accounts))
  account_ids_are_unique = (
    length(local.active_account_ids) == length(distinct(local.active_account_ids))
  )

  # A normalized context object gives downstream stacks one predictable shape
  # while retaining the complete source account record.
  account_context = {
    for name, account in local.accounts :
    name => {
      key                 = name
      account_id          = try(account.account_id, null)
      account_name        = try(account.account_name, name)
      account_type        = try(account.account_type, null)
      environment         = try(account.environment, null)
      organizational_unit = try(account.organizational_unit, null)
      criticality         = try(account.criticality, null)
      primary_region      = try(account.primary_region, local.primary_region)
      enabled_regions     = try(account.enabled_regions, local.enabled_region_names)
      raw                 = account
    }
  }

  # Tags supplied by CI/CD are intentionally exposed separately. They are not
  # merged into defaults because catalog placeholders must never become
  # resource tags accidentally.
  common_tags = merge(
    try(local.tags_catalog_locals.common_tags, {}),
    try(local.tags_catalog_locals.automation_tags, {})
  )
  environment_tags = try(local.tags_catalog_locals.environment_tags, {})
  account_tags     = try(local.tags_catalog_locals.account_tags, {})
  deployment_tags  = try(local.tags_catalog_locals.deployment_tags, {})

  tags_by_account = {
    for name, account in local.accounts :
    name => merge(
      local.common_tags,
      try(local.environment_tags[account.environment], {}),
      try(local.account_tags[name], {}),
      try(account.additional_tags, {})
    )
  }

  # Module sources, versions, groups, and requirements are projected directly
  # from module-versions.hcl. That catalog follows the companion repository's
  # module/<module-name>/v<semver> release convention.
  module_config = try(local.module_versions_catalog_locals.module_config, {})
  modules       = try(local.module_versions_catalog_locals.modules, {})
  modules_with_source = try(
    local.module_versions_catalog_locals.modules_with_source,
    {}
  )
  module_names = sort(keys(local.modules_with_source))
  module_sources = {
    for name, module in local.modules_with_source :
    name => try(module.source, null)
  }
  module_versions = {
    for name, module in local.modules_with_source :
    name => try(module.version, null)
  }
  module_digests = {
    for name, module in local.modules_with_source :
    name => try(module.digest, null)
  }
  module_requirements = try(
    local.module_versions_catalog_locals.module_requirements,
    {}
  )
  module_groups = try(local.module_versions_catalog_locals.module_groups, {})
  module_compatibility = try(
    local.module_versions_catalog_locals.compatibility,
    {}
  )
  deprecated_modules = try(
    local.module_versions_catalog_locals.deprecated_modules,
    {}
  )

  # Validation results from catalogs are exposed for CI/precondition consumers;
  # this layer does not turn placeholder catalog data into deployment errors.
  catalog_validation = {
    accounts = {
      ids_are_unique = local.account_ids_are_unique
      source         = try(local.accounts_catalog_locals.account_ids_are_unique, null)
    }
    regions = try(local.regions_catalog_locals.region_catalog_validation, {})
  }
}
