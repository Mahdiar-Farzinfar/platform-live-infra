# Task wrapper for developer convenience.
# Taskfile.yml is the source of truth for task names, descriptions, and behavior.
# This Makefile only delegates to Task; add workflow logic to Taskfile.yml, not here.
# Pass Task variables (for example TARGET, CHECK, APPLY, TG_ARGS, or CLI_ARGS)
# through the environment; arbitrary Make argument forwarding is not implemented.

.DEFAULT_GOAL := help

.PHONY: help default verify-env fmt fmt\:terraform fmt\:terragrunt\:hcl validate \
	verify\:security-baseline \
	validate\:terraform validate\:terragrunt\:hcl validate\:scp\:json lint \
	lint\:terraform lint\:actions lint\:yaml lint\:markdown lint\:shell scan\:checkov \
	scan\:trivy\:config scan\:trivy\:fs scan\:gitleaks security-all pre-commit ci init \
	render\:terragrunt init-validate-plan plan apply drift changed-stacks \
	drift\:ci plan-matrix bootstrap\:create-backend bootstrap\:migrate-to-remote clean

help:
	@task help

default:
	@task default

verify-env:
	@task verify-env

verify\:security-baseline:
	@task verify:security-baseline

verify\:post-apply:
	@task verify:post-apply

fmt:
	@task fmt

fmt\:terraform:
	@task fmt:terraform

fmt\:terragrunt\:hcl:
	@task fmt:terragrunt:hcl

validate:
	@task validate

validate\:terraform:
	@task validate:terraform

validate\:terragrunt\:hcl:
	@task validate:terragrunt:hcl

validate\:scp\:json:
	@task validate:scp:json

lint:
	@task lint

lint\:terraform:
	@task lint:terraform

lint\:actions:
	@task lint:actions

lint\:yaml:
	@task lint:yaml

lint\:markdown:
	@task lint:markdown

lint\:shell:
	@task lint:shell

scan\:checkov:
	@task scan:checkov

scan\:trivy\:config:
	@task scan:trivy:config

scan\:trivy\:fs:
	@task scan:trivy:fs

scan\:gitleaks:
	@task scan:gitleaks

security-all:
	@task security-all

pre-commit:
	@task pre-commit

ci:
	@task ci

init:
	@task init

render\:terragrunt:
	@task render:terragrunt

init-validate-plan:
	@task init-validate-plan

plan:
	@task plan

apply:
	@task apply

drift:
	@task drift

changed-stacks:
	@task changed-stacks

plan-matrix:
	@task plan-matrix

bootstrap\:create-backend:
	@task bootstrap:create-backend

bootstrap\:migrate-to-remote:
	@task bootstrap:migrate-to-remote

clean:
	@task clean
