# Security foundation region context for us-east-1 descendants.
#
# This file is intentionally resource-free. Leaf stacks own module sources and
# inputs; shared _envcommon layers own provider, backend, and tag generation.

locals {
  # Load the canonical region projection without relying on the local machine's
  # AWS_REGION or provider configuration.
  common = read_terragrunt_config(
    "${get_repo_root()}/live/common.hcl"
  )
  common_locals = try(local.common.locals, {})
  _account      = read_terragrunt_config(find_in_parent_folders("account.hcl"))

  region_key = "us-east-1"
  regions    = try(local.common_locals.regions, {})
  region     = try(local.regions[local.region_key], {})

  # The catalog's name is authoritative when present; the path's canonical key
  # is the deterministic authoring-time fallback and never uses ambient state.
  aws_region  = try(local.region.name, local.region_key)
  name        = local.aws_region
  region_name = local.aws_region

  description            = try(local.region.description, null)
  enabled                = try(local.region.enabled, false)
  primary                = try(local.region.primary, false)
  cost_tier              = try(local.region.cost_tier, null)
  compliance_eligibility = try(local.region.compliance_eligibility, [])
  service_availability   = try(local.region.service_availability, {})

  account_key = try(local._account.locals.account_key, null)
  account_catalog_key = try(
    local._account.locals.catalog_account_key,
    local.account_key
  )
  account_id      = try(local._account.locals.account_id, null)
  account_context = try(local._account.locals.account_context, {})
  account_enabled_regions = try(
    local._account.locals.enabled_regions,
    []
  )
  enabled_for_account = contains(
    local.account_enabled_regions,
    local.region_key
  )

  region_context = {
    key                    = local.region_key
    name                   = local.aws_region
    description            = local.description
    enabled                = local.enabled
    primary                = local.primary
    cost_tier              = local.cost_tier
    compliance_eligibility = local.compliance_eligibility
    service_availability   = local.service_availability
    account_key            = local.account_key
    account_catalog_key    = local.account_catalog_key
    account_id             = local.account_id
    enabled_for_account    = local.enabled_for_account
    account                = local.account_context
    raw                    = local.region
  }
}
