# live/catalogs/tags.hcl
# ==============================================================================
# Centralized Tag Catalog
# ==============================================================================
# This catalog defines standard tags that should be applied across all
# infrastructure resources for governance, cost tracking, and compliance.
#
# Usage in terragrunt.hcl:
#   include "tags" {
#     path = find_in_parent_folders("catalogs/tags.hcl")
#   }
#
#   inputs = {
#     tags = merge(
#       include.tags.locals.common_tags,
#       include.tags.locals.environment_tags["prod"],
#       {
#         Component = "api-gateway"
#       }
#     )
#   }
# ==============================================================================

locals {
  # ==============================================================================
  # Common Tags - Applied to ALL resources
  # ==============================================================================
  common_tags = {
    # Infrastructure Management
    ManagedBy  = "Terragrunt"
    IaC        = "true"
    Repository = "github.com/Mahdiar-Farzinfar/platform-live-infra"

    # Organization
    Organization = "personal"

    # Compliance & Security
    ComplianceScope = "not-applicable" # e.g., "SOC2", "HIPAA", "PCI-DSS", "GDPR"

    # Contact & Ownership
    TechnicalOwner = "mahdiarfarzinfar@gmail.com"
    BusinessOwner  = "mahdiarfarzinfar@gmail.com"

    # Cost Management
    CostCenter = "personal-infrastructure"
  }

  # ==============================================================================
  # Environment-Specific Tags
  # ==============================================================================
  environment_tags = {
    sandbox = {
      Environment     = "sandbox"
      EnvironmentType = "non-production"
    }
  }

  # ==============================================================================
  # Account-Specific Tags
  # ==============================================================================
  account_tags = {
    management = {
      AccountPurpose = "management"
      AccountType    = "foundation"
      Workload       = "organization-management"
    }

    security = {
      AccountPurpose = "security"
      AccountType    = "foundation"
      Workload       = "security-monitoring"
    }

    log-archive = {
      AccountPurpose = "log-archive"
      AccountType    = "foundation"
      Workload       = "centralized-logging"
      RetentionYears = "1"
    }

    sandbox-account = {
      AccountPurpose = "sandbox"
      AccountType    = "workload"
      Workload       = "sandbox"
    }
  }

  # ==============================================================================
  # Automation Tags
  # ==============================================================================
  automation_tags = {
    GitHubActionsDeployment = "true"
  }

  # ==============================================================================
  # Operational Tags
  # ==============================================================================
  # These should be injected during deployment via CI/CD
  deployment_tags = {
    DeploymentId        = "TBD" # Unique deployment identifier
    DeploymentTimestamp = "TBD" # ISO 8601 timestamp
    CommitSHA           = "TBD" # Git commit hash
    PipelineId          = "TBD" # CI/CD pipeline run ID
    DeployedBy          = "TBD" # Service account or user
  }
}
# ==============================================================================
# Tag Validation Rules (Documentation)
# ==============================================================================
# The following rules should be enforced via AWS Organizations Tag Policies
# or CI/CD validation:
#
# 1. Required tags on all resources:
#    - Environment
#    - ManagedBy
#    - CostCenter
#    - TechnicalOwner
#
# 2. Tag key format: PascalCase
# 3. Tag value format: lowercase-with-dashes (except for emails and URLs)
# 4. Maximum tags per resource: 50 (AWS limit)
# 5. Tag names cannot exceed 128 characters
# 6. Tag values cannot exceed 256 characters
# ==============================================================================
