# Convenience wrapper around Taskfile.yml.
# Taskfile.yml remains the source of truth for task names, dependencies, and behavior.
# Pass Task variables such as TARGET, CHECK, APPLY, TG_ARGS, or CLI_ARGS through
# the environment. Argument quoting remains Task's responsibility.

set windows-shell := ["powershell.exe", "-NoProfile", "-Command"]

default:
    task help

help:
    task help

verify-env:
    task verify-env

verify-security-baseline:
    task verify:security-baseline

verify-post-apply:
    task verify:post-apply

fmt:
    task fmt

fmt-terraform:
    task fmt:terraform

fmt-terragrunt-hcl:
    task fmt:terragrunt:hcl

validate:
    task validate

validate-terraform:
    task validate:terraform

validate-terragrunt-hcl:
    task validate:terragrunt:hcl

validate-scp-json:
    task validate:scp:json

lint:
    task lint

lint-terraform:
    task lint:terraform

lint-actions:
    task lint:actions

lint-yaml:
    task lint:yaml

lint-markdown:
    task lint:markdown

lint-shell:
    task lint:shell

scan-checkov:
    task scan:checkov

scan-trivy-config:
    task scan:trivy:config

scan-trivy-fs:
    task scan:trivy:fs

scan-gitleaks:
    task scan:gitleaks

security-all:
    task security-all

pre-commit:
    task pre-commit

ci:
    task ci

init:
    task init

render-terragrunt:
    task render:terragrunt

init-validate-plan:
    task init-validate-plan

plan:
    task plan

apply:
    task apply

drift:
    task drift

changed-stacks:
    task changed-stacks

plan-matrix:
    task plan-matrix

bootstrap-create-backend:
    task bootstrap:create-backend

bootstrap-migrate-to-remote:
    task bootstrap:migrate-to-remote

clean:
    task clean
