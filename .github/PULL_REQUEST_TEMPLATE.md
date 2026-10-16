# Pull Request

## Description

### Summary
<!-- Provide a clear and concise description of the changes in this PR -->

### Motivation and Context
<!-- Why is this change required? What problem does it solve? -->
<!-- If it fixes an open issue, please link to the issue here using #issue_number -->

### Related Issues/Tickets
<!-- Link to related issues, tickets, or documentation -->
- Fixes #
- Related to #

---

## Type of Change

<!-- Mark all that apply with an 'x' -->

- [ ] 🆕 New infrastructure/resource
- [ ] ✨ Enhancement to existing infrastructure
- [ ] 🐛 Bug fix (non-breaking change that fixes an issue)
- [ ] 🔧 Configuration change
- [ ] 📝 Documentation update
- [ ] ♻️ Refactoring (no functional changes)
- [ ] 🔐 Security improvement
- [ ] 💥 Breaking change (fix or feature that would cause existing functionality to change)
- [ ] 🗑️ Resource deletion/retirement

---

## Affected Infrastructure

### Accounts
<!-- Mark all affected AWS accounts -->

- [ ] Management
- [ ] Log Archive
- [ ] Security
- [ ] Sandbox
- [ ] Production
- [ ] Other: _____________

### Regions
<!-- List all affected regions -->

- [ ] us-east-1
- [ ] us-west-2
- [ ] Other: _____________

### Stacks/Modules Changed
<!-- List all Terragrunt stacks or Terraform modules modified -->
```text
Example:
- live/foundation/security/us-east-1/cloudtrail/
- live/workloads/production/us-east-1/vpc/
```

### Resource Impact
<!-- Describe what resources will be created, modified, or destroyed -->

- **Created:**
- **Modified:**
- **Destroyed:**

---

## Testing

### Pre-Deployment Testing

- [ ] `terragrunt validate` passes for all affected stacks
- [ ] `terragrunt plan` reviewed and outputs match expectations
- [ ] `tflint` passes with no errors
- [ ] `checkov` security scan passes (or exceptions documented)
- [ ] `trivy` scan passes (or exceptions documented)
- [ ] No sensitive data exposed in plan output
- [ ] Cross-platform compatibility verified (if applicable)

### Test Environment
<!-- Describe testing performed before this PR -->

- [ ] Tested in sandbox/non-production account
- [ ] Validated state file operations
- [ ] Verified module version pinning
- [ ] Tested rollback procedure (if applicable)

### Test Results
<!-- Provide evidence of testing: plan outputs, test account results, etc. -->

<details>
<summary>Terraform Plan Output</summary>

terraform
<!-- Paste sanitized plan output here -->

</details>

---

## Security & Compliance

### Security Considerations

- [ ] No hardcoded secrets or credentials
- [ ] Secrets stored in AWS Secrets Manager/Parameter Store
- [ ] IAM policies follow least privilege principle
- [ ] Encryption at rest enabled (where applicable)
- [ ] Encryption in transit enabled (where applicable)
- [ ] Security group rules reviewed and justified
- [ ] CloudTrail logging maintained/enhanced
- [ ] GuardDuty impact assessed

### Compliance Checklist

- [ ] Changes comply with organizational SCPs
- [ ] Tagging standards followed (see `catalogs/tags.hcl`)
- [ ] Resource naming conventions adhered to
- [ ] Cost implications documented
- [ ] Backup/disaster recovery considered

### Required Approvals
<!-- Mark required approvals based on change scope -->

- [ ] Infrastructure team approval
- [ ] Security team approval (for security-related changes)
- [ ] FinOps approval (for cost-impacting changes > $X/month)
- [ ] Compliance team approval (for regulated workloads)

---

## Breaking Changes

### Impact Assessment
<!-- If this is a breaking change, describe the impact -->

- [ ] No breaking changes
- [ ] Breaking changes (describe below)

**Breaking Change Description:**
<!-- Detail what will break and why -->

**Migration Path:**
<!-- Describe how to handle the breaking change -->

**Rollback Plan:**
<!-- Describe how to rollback if issues arise -->

---

## Documentation

- [ ] README.md updated (if applicable)
- [ ] `docs/` updated with new procedures or architecture changes
- [ ] `CHANGELOG.md` updated
- [ ] Inline code comments added for complex logic
- [ ] Module documentation generated/updated
- [ ] Runbook/operational procedures updated (if applicable)
- [ ] `deployment-order.yaml` updated (if dependencies changed)

---

## Deployment Plan

### Deployment Order
<!-- Specify the order in which stacks must be deployed -->

1.
2.
3.

### Deployment Method

- [ ] Automated via GitHub Actions (workflow: _____________)
- [ ] Manual deployment required
- [ ] Requires maintenance window

### Deployment Dependencies
<!-- List any prerequisites or dependencies -->

-

### Estimated Deployment Time
<!-- How long will this take to apply? -->

- **Estimated time:**

### Maintenance Window Required?

- [ ] Yes (Date/Time: _____________)
- [ ] No

---

## Post-Deployment Verification

### Verification Steps
<!-- List steps to verify successful deployment -->

- [ ] Resources created successfully
- [ ] Application health checks pass
- [ ] Monitoring/alerting functional
- [ ] Logs flowing to Log Archive account
- [ ] Cost tracking tags applied correctly
- [ ] Security baseline checks pass (see `tests/smoke/`)
- [ ] Integration tests pass

### Monitoring
<!-- What metrics/logs should be monitored post-deployment? -->

-

### Rollback Criteria
<!-- Under what conditions should this change be rolled back? -->

-

---

## Additional Notes

### Known Issues/Limitations
<!-- Document any known issues or limitations -->

### Future Improvements
<!-- Note any follow-up work or technical debt -->

### Dependencies
<!-- List external dependencies: module versions, provider versions, etc. -->

---

## Checklist

### Before Requesting Review

- [ ] PR title follows convention: `[type]: brief description`
- [ ] Branch name follows convention
- [ ] All CI/CD checks passing
- [ ] Self-review completed
- [ ] Code follows project style guidelines
- [ ] No unrelated changes included
- [ ] Commits are atomic and well-described

### Before Merge

- [ ] Required approvals obtained
- [ ] All review comments addressed
- [ ] Final plan reviewed and approved
- [ ] Deployment scheduled (if required)
- [ ] Stakeholders notified (if required)
- [ ] Post-deployment verification plan ready

---

## Screenshots/Diagrams
<!-- If applicable, add screenshots or architecture diagrams -->

---

## References
<!-- Link to relevant documentation, ADRs, RFCs, or external resources -->

-
