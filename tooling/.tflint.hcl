# TFLint Configuration
# Enterprise-grade linting rules for Terraform/Terragrunt infrastructure

config {
  # Force plugin downloads even if cached versions exist
  force = false

  # Disable colored output in CI/CD environments
  # Override via CLI: --color or TF_CLI_ARGS
  disabled_by_default = false

  # Plugin directory for caching
  plugin_dir = "~/.tflint.d/plugins"

  # Parallel execution for performance
  call_module_type = "all"

  # Ignore specific modules (if needed)
  # Uncomment and adjust as necessary
  # ignore_module = {
  #   "terraform-aws-modules/vpc/aws"            = true
  #   "terraform-aws-modules/security-group/aws" = true
  # }
}

# AWS Plugin
# Validates AWS-specific resources and best practices
plugin "aws" {
  enabled = true
  version = "0.32.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"

  # Deep checking mode - validates AWS resource configurations
  # against actual AWS API constraints (requires AWS credentials)
  deep_check = false
}

# Terraform Plugin
# Enforces Terraform language best practices and conventions
plugin "terraform" {
  enabled = true
  version = "0.8.0"
  source  = "github.com/terraform-linters/tflint-ruleset-terraform"

  # Preset for opinionated recommended rules
  preset = "recommended"
}

################################################################################
# AWS-Specific Rules
################################################################################

# IAM Security Rules
rule "aws_iam_policy_document_gov_friendly_arns" {
  enabled = false # Enable if working with GovCloud
}

rule "aws_iam_role_policy_too_permissive" {
  enabled = true
}

rule "aws_iam_policy_too_permissive" {
  enabled = true
}

# S3 Security and Best Practices
rule "aws_s3_bucket_versioning_enabled" {
  enabled = true
}

rule "aws_s3_bucket_encryption_enabled" {
  enabled = true
}

rule "aws_s3_bucket_public_access_block_enabled" {
  enabled = true
}

rule "aws_s3_bucket_lifecycle_rule_enabled" {
  enabled = true
}

# EC2 and Compute Rules
rule "aws_instance_invalid_type" {
  enabled = true
}

rule "aws_instance_previous_type" {
  enabled = true
}

rule "aws_launch_configuration_invalid_image_id" {
  enabled = true
}

rule "aws_launch_template_invalid_instance_type" {
  enabled = true
}

# Database Rules
rule "aws_db_instance_invalid_type" {
  enabled = true
}

rule "aws_db_instance_previous_type" {
  enabled = true
}

rule "aws_elasticache_cluster_invalid_type" {
  enabled = true
}

rule "aws_elasticache_cluster_previous_type" {
  enabled = true
}

# Network and VPC Rules
rule "aws_security_group_invalid_ingress_cidr" {
  enabled = true
}

rule "aws_security_group_invalid_egress_cidr" {
  enabled = true
}

rule "aws_route_not_specified_target" {
  enabled = true
}

rule "aws_route_specified_multiple_targets" {
  enabled = true
}

# Resource Naming and Tagging
rule "aws_resource_missing_tags" {
  enabled = true
  tags = [
    "Environment",
    "ManagedBy",
    "Project",
    "Owner"
  ]
  exclude = [
    "aws_iam_role",
    "aws_iam_policy",
    "aws_iam_user",
    "aws_iam_group"
  ]
}

################################################################################
# Terraform Language Rules
################################################################################

# Naming Conventions
rule "terraform_naming_convention" {
  enabled = true

  # Resource naming format
  resource {
    format = "snake_case"
  }

  # Variable naming format
  variable {
    format = "snake_case"
  }

  # Output naming format
  output {
    format = "snake_case"
  }

  # Module naming format
  module {
    format = "snake_case"
  }

  # Data source naming format
  data {
    format = "snake_case"
  }

  # Local value naming format
  locals {
    format = "snake_case"
  }
}

# Documentation Rules
rule "terraform_documented_outputs" {
  enabled = true
}

rule "terraform_documented_variables" {
  enabled = true
}

rule "terraform_comment_syntax" {
  enabled = true
}

# Type and Variable Rules
rule "terraform_typed_variables" {
  enabled = true
}

rule "terraform_unused_declarations" {
  enabled = true
}

rule "terraform_unused_required_providers" {
  enabled = true
}

# Module Rules
rule "terraform_module_pinned_source" {
  enabled = true
  style   = "semver"        # Enforce semantic versioning
  default_branches = [
    "main",
    "master"
  ]
}

rule "terraform_module_version" {
  enabled = true
  exact   = false           # Allow version constraints like ~> 1.0
}

# Deprecated Syntax
rule "terraform_deprecated_index" {
  enabled = true
}

rule "terraform_deprecated_interpolation" {
  enabled = true
}

rule "terraform_deprecated_lookup" {
  enabled = true
}

# Workspace and State
rule "terraform_workspace_remote" {
  enabled = true
}

# Standard Module Structure
rule "terraform_standard_module_structure" {
  enabled = true
}

# Required Version Constraints
rule "terraform_required_version" {
  enabled = true
}

rule "terraform_required_providers" {
  enabled = true
}

# Empty/Unnecessary Blocks
rule "terraform_empty_list_equality" {
  enabled = true
}

################################################################################
# Custom Overrides (Optional)
################################################################################

# Disable specific rules that may not align with your workflow
# Uncomment and adjust as necessary

# rule "aws_db_instance_invalid_db_subnet_group" {
#   enabled = false
# }

# rule "terraform_naming_convention" {
#   enabled = false
# }
