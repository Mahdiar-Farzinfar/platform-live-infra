# Shared tag composition for live descendant stacks.
#
# Include from a stack with:
#   include "tagging" {
#     path   = find_in_parent_folders("_envcommon/tagging.hcl")
#     expose = true
#   }
#
# The resulting `tags` input is compatible with every current platform module.
# Stack-specific tags should be merged before `include.tagging.locals.tags` so
# catalog-governed values remain authoritative.

locals {
  repository_root = get_repo_root()
  live_root       = "${local.repository_root}/live"

  common = try(
    read_terragrunt_config("${local.live_root}/common.hcl"),
    {}
  )
  common_locals = try(local.common.locals, {})

  # Account and Region files are optional while the hierarchy is authored.
  # No caller identity or AWS API lookup is used to infer missing context.
  account_config = try(
    read_terragrunt_config(find_in_parent_folders("account.hcl")),
    {}
  )
  region_config = try(
    read_terragrunt_config(find_in_parent_folders("region.hcl")),
    {}
  )
  account_locals = try(local.account_config.locals, {})
  region_locals  = try(local.region_config.locals, {})

  account_key = try(
    local.account_locals.account_key,
    local.account_locals.account_name,
    local.account_locals.name,
    null
  )
  account_catalog_key = try(
    local.account_locals.catalog_account_key,
    local.account_key
  )
  account = try(
    local.common_locals.accounts[local.account_catalog_key],
    local.common_locals.accounts[replace(local.account_catalog_key, "-", "_")],
    {}
  )

  environment = try(
    local.account_locals.environment,
    local.account.environment,
    null
  )
  aws_region = try(
    local.region_locals.aws_region,
    local.region_locals.region,
    local.region_locals.name,
    null
  )

  platform_tags = try(local.common_locals.common_tags, {})
  catalog_environment_tags = try(
    local.common_locals.environment_tags[local.environment],
    {}
  )
  catalog_account_tags = try(
    local.common_locals.account_tags[local.account_key],
    local.common_locals.account_tags[local.account_catalog_key],
    local.common_locals.account_tags[replace(local.account_key, "_", "-")],
    {}
  )
  account_additional_tags = try(local.account.additional_tags, {})

  # Environment and CostCenter are existing catalog keys whose authoritative
  # values come from account metadata when available. Null or empty values are
  # omitted rather than converted into misleading defaults.
  derived_context_tags = {
    for key, value in {
      Environment = local.environment
      CostCenter  = try(local.account.cost_center, null)
    } :
    key => tostring(value)
    if value != null && try(trimspace(tostring(value)), "") != ""
  }

  # Precedence, lowest to highest:
  # account additions -> account catalog -> environment catalog ->
  # platform catalog -> authoritative account context.
  #
  # Platform and derived context values are last so catalog-governed keys
  # cannot be silently replaced by account or stack metadata.
  tags = merge(
    local.account_additional_tags,
    local.catalog_account_tags,
    local.catalog_environment_tags,
    local.platform_tags,
    local.derived_context_tags
  )

  required_tag_keys = [
    "Environment",
    "ManagedBy",
    "CostCenter",
    "TechnicalOwner",
  ]
  protected_tag_keys = sort(distinct(concat(
    keys(local.platform_tags),
    keys(local.derived_context_tags)
  )))
  missing_required_tag_keys = sort([
    for key in local.required_tag_keys :
    key
    if try(trimspace(tostring(local.tags[key])), "") == ""
  ])

  # Deployment tags are CI-provided operational metadata and may contain
  # authoring placeholders. They are exposed for validation but are never
  # merged into resource tags automatically.
  deployment_tags = try(local.common_locals.deployment_tags, {})

  tag_context = {
    account_key               = local.account_key
    account_catalog_key       = local.account_catalog_key
    environment               = local.environment
    region                    = local.aws_region
    required_tag_keys         = local.required_tag_keys
    protected_tag_keys        = local.protected_tag_keys
    missing_required_tag_keys = local.missing_required_tag_keys
  }
}

inputs = {
  tags = local.tags
}
