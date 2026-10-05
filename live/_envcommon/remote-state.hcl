# Shared remote-state configuration for live descendant stacks.
#
# Include from a deployable stack with:
#   include "remote_state" {
#     path   = find_in_parent_folders("_envcommon/remote-state.hcl")
#     expose = true
#   }
#
# The backend-bootstrap module is intentionally excluded from this layer. It
# must first run with local state, create the S3 bucket and DynamoDB table, and
# then be migrated with `terraform init -migrate-state`.

locals {
  repository_root = get_repo_root()
  live_root       = "${local.repository_root}/live"

  common = try(
    read_terragrunt_config("${local.live_root}/common.hcl"),
    {}
  )
  common_locals = try(local.common.locals, {})

  # Account and region metadata are optional while the hierarchy is being
  # authored. No AWS API calls or credential lookups are performed here.
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
  account_id = try(
    local.account_locals.account_id,
    try(local.common_locals.account_ids[local.account_key], null),
    null
  )
  aws_region = try(
    local.region_locals.aws_region,
    local.region_locals.region,
    local.region_locals.name,
    null
  )

  # Backend metadata is intentionally data-driven. The catalogs currently do
  # not define a bucket/table/name prefix, so these remain null until bootstrap
  # outputs or an approved backend catalog projection is added.
  backend_catalog = try(
    local.common_locals.backend,
    local.common_locals.remote_state,
    {}
  )
  backend_bucket = try(
    local.backend_catalog.bucket,
    local.backend_catalog.state_bucket_name,
    null
  )
  backend_region = try(
    local.backend_catalog.region,
    local.backend_catalog.state_bucket_region,
    local.aws_region,
    null
  )
  backend_lock_table = try(
    local.backend_catalog.dynamodb_table,
    local.backend_catalog.lock_table_name,
    null
  )
  backend_kms_key_id = try(
    local.backend_catalog.kms_key_id,
    local.backend_catalog.kms_key_arn,
    null
  )

  # The hierarchy path is the stable identity for a stack. Account and Region
  # directories must remain part of that hierarchy, so TBD account IDs cannot
  # collapse otherwise distinct states into the same key.
  state_key = "${path_relative_to_include()}/terraform.tfstate"

  backend_context = {
    bucket         = local.backend_bucket
    region         = local.backend_region
    dynamodb_table = local.backend_lock_table
    kms_key_id     = local.backend_kms_key_id
    account_key    = local.account_key
    account_id     = local.account_id
    aws_region     = local.aws_region
    key            = local.state_key
  }
}

remote_state {
  backend = "s3"

  # No local-backend or empty-value fallback is provided. Before deployment,
  # backend metadata must be populated from the approved bootstrap outputs (or
  # an approved catalog projection); otherwise backend initialization fails.
  config = {
    bucket         = local.backend_context.bucket
    key            = local.backend_context.key
    region         = local.backend_context.region
    dynamodb_table = local.backend_context.dynamodb_table

    # The bootstrap module requires a customer-managed KMS key and rejects
    # non-KMS writes through its bucket policy.
    encrypt    = true
    kms_key_id = local.backend_context.kms_key_id
  }

  generate = {
    path      = "backend.tf"
    if_exists = "overwrite_terragrunt"
  }
}
