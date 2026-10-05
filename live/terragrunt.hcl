# Root Terragrunt configuration for all live infrastructure stacks.
#
# Descendant stacks should include this file with:
#   include "root" {
#     path   = find_in_parent_folders("terragrunt.hcl")
#     expose = true
#   }
#
# This root deliberately does not define a provider or remote state backend.
# Account/region targeting and backend settings vary by stack and are not yet
# represented by a dedicated _envcommon layer. Keeping those concerns out of
# this file also preserves the local-state bootstrap flow for backend-bootstrap.

locals {
  repository_root = get_repo_root()
  live_root       = "${local.repository_root}/live"
  catalog_root    = "${local.live_root}/catalogs"

  # common.hcl is the shared projection layer for all catalogs. Loading it once
  # here gives child stacks a stable, exposed contract without duplicating
  # catalog reads or creating an include cycle.
  common = read_terragrunt_config("${local.live_root}/common.hcl")

  common_locals = try(local.common.locals, {})

  # Explicit aliases make the root contract discoverable and keep consumers
  # independent of the implementation details inside common.hcl.
  accounts             = try(local.common_locals.accounts, {})
  account_context      = try(local.common_locals.account_context, {})
  active_accounts      = try(local.common_locals.active_accounts, {})
  regions              = try(local.common_locals.regions, {})
  enabled_regions      = try(local.common_locals.enabled_regions, {})
  primary_region       = try(local.common_locals.primary_region, null)
  common_tags          = try(local.common_locals.common_tags, {})
  environment_tags     = try(local.common_locals.environment_tags, {})
  account_tags         = try(local.common_locals.account_tags, {})
  tags_by_account      = try(local.common_locals.tags_by_account, {})
  module_sources       = try(local.common_locals.module_sources, {})
  module_versions      = try(local.common_locals.module_versions, {})
  module_digests       = try(local.common_locals.module_digests, {})
  module_requirements  = try(local.common_locals.module_requirements, {})
  module_groups        = try(local.common_locals.module_groups, {})
  module_compatibility = try(local.common_locals.module_compatibility, {})
}
