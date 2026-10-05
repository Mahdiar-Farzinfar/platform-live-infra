# ./live/catalogs/regions.hcl
# Regional configuration catalog

locals {
  regions = {
    "us-east-1" = {
      name        = "us-east-1"
      description = "US East (N. Virginia)"
      enabled     = true
      primary     = true
      cost_tier   = "standard"

      # Regulatory eligibility only.
      # This does not automatically make workloads compliant.
      compliance_eligibility = [
        "FedRAMP",
        "HIPAA",
        "PCI-DSS",
      ]

      # Regional service availability only.
      # These services still need to be enabled and configured per account.
      service_availability = {
        guardduty   = true
        securityhub = true
        cloudtrail  = true
        config      = true
      }
    }
  }

  valid_cost_tiers = [
    "standard",
    "premium",
  ]

  primary_region_candidates = [
    for region_key, region_config in local.regions :
    region_key
    if region_config.primary
  ]

  region_catalog_validation = {
    primary_region_count = (
      length(local.primary_region_candidates) == 1
      ? null
      : tobool("ERROR: Exactly one region must have primary = true.")
    )

    primary_region_enabled = (
      local.regions[one(local.primary_region_candidates)].enabled
      ? null
      : tobool("ERROR: The primary region must also have enabled = true.")
    )

    region_names_match_keys = (
      alltrue([
        for region_key, region_config in local.regions :
        region_key == region_config.name
      ])
      ? null
      : tobool("ERROR: Each region map key must match the region name attribute.")
    )

    valid_cost_tiers = (
      alltrue([
        for region_key, region_config in local.regions :
        contains(local.valid_cost_tiers, region_config.cost_tier)
      ])
      ? null
      : tobool("ERROR: Every region must use a supported cost_tier.")
    )
  }

  primary_region = one(local.primary_region_candidates)

  enabled_regions = {
    for region_key, region_config in local.regions :
    region_key => region_config
    if region_config.enabled
  }

  enabled_region_names = sort([
    for region_key, region_config in local.regions :
    region_key
    if region_config.enabled
  ])

  compliance_eligibility = {
    for compliance_type in [
      "GDPR",
      "FedRAMP",
      "HIPAA",
      "PCI-DSS",
    ] :
    compliance_type => sort([
      for region_key, region_config in local.regions :
      region_key
      if region_config.enabled
      && contains(
        region_config.compliance_eligibility,
        compliance_type
      )
    ])
  }
}
