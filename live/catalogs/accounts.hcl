# ./live/catalogs/accounts.hcl
# Account catalog for multi-account AWS Organization
# This file serves as the single source of truth for all AWS accounts in the organization

locals {
  # Account structure following AWS Control Tower / Landing Zone best practices
  accounts = {
    # =========================================================================
    # FOUNDATION ACCOUNTS
    # Core accounts required for security, compliance, and centralized logging
    # =========================================================================

    management = {
      account_id          = "TBD" # AWS Organization root account ID
      account_name        = "organization-management"
      email               = "mahdiarfarzinfar+management@gmail.com"
      organizational_unit = "Root"

      # Account classification
      account_type = "management"
      environment  = "foundation"
      criticality  = "critical"

      # Compliance and governance
      compliance_frameworks = ["SOC2", "ISO27001", "PCI-DSS"]
      data_classification   = "confidential"
      backup_required       = true

      # Cost allocation
      cost_center         = "PLATFORM"
      budget_alert_emails = ["mahdiarfarzinfar@gmail.com"]
      monthly_budget_usd  = null

      # Access control
      sso_permission_sets = ["AdministratorAccess", "ReadOnlyAccess"]
      break_glass_users   = ["mahdiarfarzinfar@gmail.com"] # Emergency access users

      # Operational metadata
      primary_region      = "us-east-1"
      enabled_regions     = ["us-east-1"]
      cloudtrail_enabled  = true
      guardduty_enabled   = true
      securityhub_enabled = true
      config_enabled      = true

      # Contact information
      technical_owner  = "Mahdiar Farzinfar"
      business_owner   = "Mahdiar Farzinfar"
      incident_contact = "mahdiarfarzinfar@gmail.com"

      # Tagging strategy
      additional_tags = {
        "AccountPurpose" = "OrganizationManagement"
        "ManagedBy"      = "Terraform"
        "Repository"     = "platform-live-infra"
      }
    }

    log_archive = {
      account_id          = "TBD"
      account_name        = "security-log-archive"
      email               = "mahdiarfarzinfar+log-archive@gmail.com"
      organizational_unit = "Security"

      account_type = "log_archive"
      environment  = "foundation"
      criticality  = "critical"

      compliance_frameworks = ["SOC2", "ISO27001", "PCI-DSS", "HIPAA"]
      data_classification   = "confidential"
      backup_required       = true
      retention_years       = 7 # Compliance-driven retention period

      cost_center         = "SECURITY"
      budget_alert_emails = ["mahdiarfarzinfar@gmail.com"]
      monthly_budget_usd  = null

      sso_permission_sets = ["SecurityAuditAccess", "ReadOnlyAccess"]
      break_glass_users   = ["mahdiarfarzinfar@gmail.com"]

      primary_region      = "us-east-1"
      enabled_regions     = ["us-east-1"]
      cloudtrail_enabled  = true
      guardduty_enabled   = true
      securityhub_enabled = true
      config_enabled      = true

      # Log archive specific settings
      log_aggregation_enabled = true
      mfa_delete_enabled      = true
      object_lock_enabled     = true
      replication_enabled     = false
      replication_region      = null

      technical_owner  = "Mahdiar Farzinfar"
      business_owner   = "Mahdiar Farzinfar"
      incident_contact = "mahdiarfarzinfar@gmail.com"

      additional_tags = {
        "AccountPurpose" = "CentralizedLogging"
        "ManagedBy"      = "Terraform"
        "Repository"     = "platform-live-infra"
      }
    }

    security = {
      account_id          = "TBD"
      account_name        = "security-tooling"
      email               = "mahdiarfarzinfar+security@gmail.com"
      organizational_unit = "Security"

      account_type = "security"
      environment  = "foundation"
      criticality  = "critical"

      compliance_frameworks = ["SOC2", "ISO27001", "PCI-DSS"]
      data_classification   = "confidential"
      backup_required       = true

      cost_center         = "SECURITY"
      budget_alert_emails = ["mahdiarfarzinfar@gmail.com"]
      monthly_budget_usd  = null

      sso_permission_sets = ["SecurityAdministrator", "SecurityAuditAccess"]
      break_glass_users   = ["mahdiarfarzinfar@gmail.com"]

      primary_region      = "us-east-1"
      enabled_regions     = ["us-east-1"]
      cloudtrail_enabled  = true
      guardduty_enabled   = true
      securityhub_enabled = true
      config_enabled      = true

      # Security tooling specific
      guardduty_administrator   = true
      securityhub_administrator = true
      macie_enabled             = true
      access_analyzer_enabled   = true

      technical_owner  = "Mahdiar Farzinfar"
      business_owner   = "Mahdiar Farzinfar"
      incident_contact = "mahdiarfarzinfar@gmail.com"

      additional_tags = {
        "AccountPurpose" = "SecurityTooling"
        "ManagedBy"      = "Terraform"
        "Repository"     = "platform-live-infra"
      }
    }

    sandbox = {
      account_id          = "TBD"
      account_name        = "sandbox-development"
      email               = "mahdiarfarzinfar+sandbox@gmail.com"
      organizational_unit = "Workloads/Development"

      account_type = "workload"
      environment  = "sandbox"
      criticality  = "low"

      compliance_frameworks = []
      data_classification   = "internal"
      backup_required       = false

      cost_center         = "ENGINEERING"
      budget_alert_emails = ["mahdiarfarzinfar@gmail.com"]
      monthly_budget_usd  = 10 # Limit sandbox spending

      sso_permission_sets = ["DeveloperAccess", "ReadOnlyAccess"]
      break_glass_users   = []

      primary_region      = "us-east-1"
      enabled_regions     = ["us-east-1"]
      cloudtrail_enabled  = true
      guardduty_enabled   = true
      securityhub_enabled = false
      config_enabled      = false

      # Sandbox-specific controls
      auto_shutdown_enabled = true
      max_instance_types    = ["t3.medium", "t3.large"]

      technical_owner  = "Mahdiar Farzinfar"
      business_owner   = "Mahdiar Farzinfar"
      incident_contact = "mahdiarfarzinfar@gmail.com"

      additional_tags = {
        "AccountPurpose" = "DeveloperSandbox"
        "ManagedBy"      = "Terraform"
        "Repository"     = "platform-live-infra"
        "AutoShutdown"   = "enabled"
      }
    }

    # =========================================================================
    # TEMPLATE FOR ADDITIONAL ACCOUNTS
    # Uncomment and customize as needed
    # =========================================================================

    # development = {
    #   account_id          = "TBD"
    #   account_name        = "application-development"
    #   email               = "TBD"
    #   organizational_unit = "Workloads/Development"
    #
    #   account_type        = "workload"
    #   environment         = "development"
    #   criticality         = "low"
    #
    #   compliance_frameworks = []
    #   data_classification   = "internal"
    #   backup_required       = false
    #
    #   cost_center         = "TBD"
    #   budget_alert_emails = ["TBD"]
    #   monthly_budget_usd  = null
    #
    #   sso_permission_sets = ["DeveloperAccess", "ReadOnlyAccess"]
    #   break_glass_users   = []
    #
    #   primary_region      = "us-east-1"
    #   enabled_regions     = ["us-east-1"]
    #   cloudtrail_enabled  = true
    #   guardduty_enabled   = true
    #   securityhub_enabled = true
    #   config_enabled      = true
    #
    #   technical_owner     = "Mahdiar Farzinfar"
    #   business_owner      = "Mahdiar Farzinfar"
    #   incident_contact    = "mahdiarfarzinfar@gmail.com"
    #
    #   additional_tags = {
    #     "AccountPurpose" = "Development"
    #     "ManagedBy"      = "Terraform"
    #     "Repository"     = "platform-live-infra"
    #   }
    # }

    # staging = {
    #   account_id          = "TBD"
    #   account_name        = "application-staging"
    #   email               = "TBD"
    #   organizational_unit = "Workloads/PreProduction"
    #
    #   account_type        = "workload"
    #   environment         = "staging"
    #   criticality         = "medium"
    #
    #   compliance_frameworks = ["SOC2"]
    #   data_classification   = "confidential"
    #   backup_required       = true
    #
    #   cost_center         = "TBD"
    #   budget_alert_emails = ["TBD"]
    #   monthly_budget_usd  = null
    #
    #   sso_permission_sets = ["DeveloperAccess", "DeploymentAccess"]
    #   break_glass_users   = ["TBD"]
    #
    #   primary_region      = "us-east-1"
    #   enabled_regions     = ["us-east-1"]
    #   cloudtrail_enabled  = true
    #   guardduty_enabled   = true
    #   securityhub_enabled = true
    #   config_enabled      = true
    #
    #   technical_owner     = "Mahdiar Farzinfar"
    #   business_owner      = "Mahdiar Farzinfar"
    #   incident_contact    = "mahdiarfarzinfar@gmail.com"
    #
    #   additional_tags = {
    #     "AccountPurpose" = "Staging"
    #     "ManagedBy"      = "Terraform"
    #     "Repository"     = "platform-live-infra"
    #   }
    # }

    # production = {
    #   account_id          = "TBD"
    #   account_name        = "application-production"
    #   email               = "TBD"
    #   organizational_unit = "Workloads/Production"
    #
    #   account_type        = "workload"
    #   environment         = "production"
    #   criticality         = "critical"
    #
    #   compliance_frameworks = ["SOC2", "ISO27001", "PCI-DSS"]
    #   data_classification   = "confidential"
    #   backup_required       = true
    #
    #   cost_center         = "TBD"
    #   budget_alert_emails = ["TBD"]
    #   monthly_budget_usd  = null
    #
    #   sso_permission_sets = ["ProductionReadOnly", "DeploymentAccess"]
    #   break_glass_users   = ["TBD"]
    #
    #   primary_region      = "us-east-1"
    #   enabled_regions     = ["us-east-1"]
    #   cloudtrail_enabled  = true
    #   guardduty_enabled   = true
    #   securityhub_enabled = true
    #   config_enabled      = true
    #
    #   technical_owner     = "Mahdiar Farzinfar"
    #   business_owner      = "Mahdiar Farzinfar"
    #   incident_contact    = "mahdiarfarzinfar@gmail.com"
    #
    #   additional_tags = {
    #     "AccountPurpose" = "Production"
    #     "ManagedBy"      = "Terraform"
    #     "Repository"     = "platform-live-infra"
    #   }
    # }
  }

  # =========================================================================
  # HELPER LOOKUP MAPS & EXPORTS
  # Convenient data structures for dynamic consumption across the Terragrunt tree
  # =========================================================================

  # Map of account_key -> account_id
  account_ids = {
    for k, v in local.accounts : k => v.account_id
  }

  # Map of account_key -> root email address
  account_emails = {
    for k, v in local.accounts : k => v.email
  }

  # Map of account_key -> primary region
  account_primary_regions = {
    for k, v in local.accounts : k => v.primary_region
  }

  # List of foundation account keys
  foundation_account_keys = [
    for k, v in local.accounts : k if v.environment == "foundation"
  ]

  # List of workload account keys
  workload_account_keys = [
    for k, v in local.accounts : k if v.account_type == "workload"
  ]

  # Map of account_key -> valid AWS Account ID.
  # Account IDs must contain exactly 12 decimal digits.
  active_accounts = {
    for k, v in local.accounts : k => v.account_id
    if v.account_id != null && can(regex("^[0-9]{12}$", v.account_id))
  }

  # List of valid AWS Account IDs.
  active_account_ids = [
    for account_id in values(local.active_accounts) : account_id
  ]

  # Catalog integrity checks for use by Terragrunt/Terraform preconditions.
  account_ids_are_unique = (
    length(local.active_account_ids) ==
    length(distinct(local.active_account_ids))
  )

  account_emails_are_unique = (
    length(values(local.account_emails)) ==
    length(distinct(values(local.account_emails)))
  )
}
