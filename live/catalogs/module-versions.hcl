# platform-live-infra/live/catalogs/module-versions.hcl
#
# Central catalog for module versions used across all live infrastructure stacks.
# This file is the single source of truth for module version pinning.
#
# Usage:
#   Include this file in your terragrunt.hcl:
#   locals {
#     module_versions = read_terragrunt_config(find_in_parent_folders("catalogs/module-versions.hcl"))
#   }
#
#   Reference a version:
#   source = local.module_versions.locals.modules_with_source.kms.source
#
# Version Update Process:
#   1. Update version in this file
#   2. Test in sandbox/dev account first
#   3. Roll out to other environments via controlled deployment
#   4. Document changes in CHANGELOG.md

locals {
  # Base configuration for all modules
  module_config = {
    # Source type: "git", "local", "registry"
    source_type = "git"

    # Base repository URL (when using git)
    base_repo_url = "git::https://github.com/Mahdiar-Farzinfar/platform-iac-modules.git"

    # Alternative for local development
    # base_repo_url = "../../platform-iac-modules"

    # Default ref type: "tags", "branches", "commits"
    default_ref_type = "tags"
  }

  # Module versions and metadata
  # Each module entry includes:
  #   - version: Semantic version or git ref
  #   - source: Full source path (auto-generated if using standard structure)
  #   - last_verified: Last date this version was verified in production
  #   - breaking_changes: Any breaking changes to be aware of
  #   - notes: Additional context for this version
  modules = {
    # =========================================================================
    # Foundation Layer - Core Infrastructure Bootstrap
    # =========================================================================

    backend-bootstrap = {
      version          = "module/backend-bootstrap/v0.1.0"
      digest           = "a7653dd19c9e61519456c538ff212c340a2e5693"
      module_path      = "modules/backend-bootstrap"
      last_verified    = null # e.g., "2026-08-15"
      min_tf_version   = "1.6.0"
      min_aws_provider = "5.70.0"
      breaking_changes = []
      notes            = "Creates S3 backend and DynamoDB lock table for Terraform state"
      # Full source constructed dynamically below
    }

    # =========================================================================
    # Identity and Access Management
    # =========================================================================

    github-oidc = {
      version          = "module/github-oidc/v0.1.0"
      digest           = "59f5c957fed7b6b7be07884bf55c5215bc431baa"
      module_path      = "modules/github-oidc"
      last_verified    = null
      min_tf_version   = "1.6.0"
      min_aws_provider = "5.81.0"
      breaking_changes = []
      notes            = "GitHub OIDC provider for GitHub Actions authentication"
    }

    scp = {
      version          = "module/scp/v0.1.0"
      digest           = "186cb76452d9bc662417efb70cb291f0785a1512"
      module_path      = "modules/scp"
      last_verified    = null
      min_tf_version   = "1.5.0"
      min_aws_provider = "5.0"
      breaking_changes = []
      notes            = "Service Control Policies for AWS Organizations"
    }

    # =========================================================================
    # Security and Compliance
    # =========================================================================

    kms = {
      version          = "module/kms/v0.1.0"
      digest           = "aa0c8c207f0f5d2cb1fce1477071f28706e28bdb"
      module_path      = "modules/kms"
      last_verified    = null
      min_tf_version   = "1.3.0"
      min_aws_provider = "5.0"
      breaking_changes = []
      notes            = "KMS key management with rotation and multi-region support"
    }

    log-archive-bucket = {
      version          = "module/log-archive-bucket/v0.1.0"
      digest           = "7b168233edac52413be2f82cc16857bbe6ee416a"
      module_path      = "modules/log-archive-bucket"
      last_verified    = null
      min_tf_version   = "1.5.0"
      min_aws_provider = "5.0"
      breaking_changes = []
      notes            = "Centralized S3 bucket for audit logs with compliance controls"
    }

    cloudtrail = {
      version          = "module/cloudtrail/v0.1.0"
      digest           = "8085f0fcfbda02f6697e2f6bb1527bf287627683"
      module_path      = "modules/cloudtrail"
      last_verified    = null
      min_tf_version   = "1.3.0"
      min_aws_provider = "5.0"
      breaking_changes = []
      notes            = "Organization-wide CloudTrail with integrity validation"
    }

    guardduty = {
      version          = "module/guardduty/v0.1.0"
      digest           = "79bd61287350c4ee3d4c008ba25f827fb59dfea4"
      module_path      = "modules/guardduty"
      last_verified    = null
      min_tf_version   = "1.5.0"
      min_aws_provider = "5.40.0"
      breaking_changes = []
      notes            = "GuardDuty threat detection with delegated admin setup"
    }

    # =========================================================================
    # Future Modules - Placeholder for expansion
    # =========================================================================
    # Add new modules below as they are developed
    # Example structure:
    # module-name = {
    #   version          = "vX.Y.Z"
    #   module_path      = "modules/module-name"
    #   last_verified    = "YYYY-MM-DD"
    #   min_tf_version   = "1.5.0"
    #   min_aws_provider = "5.0"
    #   breaking_changes = ["Description of breaking change if any"]
    #   notes            = "Module description"
    # }
  }

  # =========================================================================
  # Dynamic Source Construction
  # =========================================================================
  # Automatically construct source URLs based on configuration.
  # Supports local development paths and versioned Git module sources.
  #
  # For Git sources, the module version is used as the ref:
  #   git::<repository>//<module_path>?ref=<version>
  #
  # A null or empty version intentionally produces a non-usable source value.
  # CI validation must prevent such modules from being used by production stacks.

  modules_with_source = {
    for name, config in local.modules : name => merge(
      config,
      {
        # Construct the full source path.
        source = (
          local.module_config.source_type == "local"
          ? "${local.module_config.base_repo_url}/${config.module_path}"
          : local.module_config.source_type == "git" && try(trimspace(config.version), "") != ""
          ? "${local.module_config.base_repo_url}//${config.module_path}?ref=${config.version}"
          : null
        )
      }
    )
  }

  # =========================================================================
  # Version Compatibility Matrix
  # =========================================================================
  # Platform-wide compatibility requirements.
  #
  # These values represent the minimum toolchain versions supported by the
  # live infrastructure catalog. The minimum Terraform and AWS provider
  # versions must be compatible with every module listed above.
  #
  # Per-module requirements are exposed separately through
  # `module_requirements` and are derived directly from `local.modules`.

  compatibility = {
    terraform = {
      # Must be equal to or greater than the highest `min_tf_version`
      # declared by any module in this catalog.
      minimum_version = "1.6.0"

      # Recommended version for local development and CI/CD execution.
      recommended_version = "1.15.6"

      # Constraint suitable for Terraform `required_version`.
      required_version_constraint = ">= 1.6.0, < 2.0.0"
    }

    terragrunt = {
      # Minimum Terragrunt version supported by this repository.
      minimum_version = "0.55.0"

      # Recommended version for local development and CI/CD execution.
      recommended_version = "1.1.1"

      # Compatibility constraint for CI/CD validation.
      required_version_constraint = ">= 0.55.0"
    }

    providers = {
      aws = {
        # Must be equal to or greater than the highest `min_aws_provider`
        # declared by any module in this catalog.
        minimum_version = "5.81.0"

        # Recommended provider version for local development and CI/CD.
        # Keep this aligned with the provider version tested by the platform.
        recommended_version = "5.81.0"

        # Constraint suitable for the AWS provider `required_providers`
        # declaration.
        required_version_constraint = ">= 5.81.0, < 6.0.0"
      }
    }
  }

  # =========================================================================
  # Per-Module Compatibility Requirements
  # =========================================================================
  # Expose the compatibility requirements declared by each module in a
  # normalized structure. This avoids duplicating module requirements in the
  # platform-level compatibility matrix and provides a single input for CI
  # validation, reporting, and compatibility checks.

  module_requirements = {
    for name, config in local.modules : name => {
      terraform = {
        minimum_version = config.min_tf_version
      }

      providers = {
        aws = {
          minimum_version = config.min_aws_provider
        }
      }
    }
  }

  # =========================================================================
  # Deprecated Modules
  # =========================================================================
  # Modules that should no longer be used
  # Keep for reference but mark as deprecated

  deprecated_modules = {
    # Example:
    # old-module-name = {
    #   deprecated_since = "2026-06-01"
    #   replacement      = "new-module-name"
    #   sunset_date      = "2026-12-01"
    #   reason           = "Replaced by improved module with better security controls"
    # }
  }

  # =========================================================================
  # Module Groups
  # =========================================================================
  # Logical grouping for bulk operations and validation

  module_groups = {
    foundation = [
      "backend-bootstrap",
    ]

    security = [
      "kms",
      "log-archive-bucket",
      "cloudtrail",
      "guardduty",
    ]

    iam = [
      "github-oidc",
      "scp",
    ]

    # All production-critical modules that require extra validation
    production_critical = [
      "backend-bootstrap",
      "kms",
      "cloudtrail",
      "guardduty",
    ]
  }
}
