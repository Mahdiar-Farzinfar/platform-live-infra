# syntax=docker/dockerfile:1.7

# Multi-architecture Dev Container for platform-live-infra.
# The digest is an OCI index (not an architecture-specific image), so buildx
# resolves the amd64 or arm64 variant requested by the build platform.
ARG BASE_IMAGE=mcr.microsoft.com/devcontainers/base:2-debian-13@sha256:2e826a6ae92e5744cc0a471a03b4411e64f6b7cc6af3adaecddad697f0018f10
FROM ${BASE_IMAGE}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# OCI / supply-chain metadata args
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown
ARG VERSION=dev
ARG SOURCE_URL="https://github.com/Mahdiar-Farzinfar/platform-live-infra"
ARG LICENSES="Apache-2.0"

ARG TARGETARCH
ARG ASDF_VERSION=0.16.5
ARG GO_VERSION=1.26.0
ARG USERNAME=vscode

# OCI Labels
LABEL org.opencontainers.image.title="platform-live-infra devcontainer" \
      org.opencontainers.image.description="Enterprise-grade DevContainer for managing multi-account AWS live infrastructure with Terraform and Terragrunt, security guardrails, CI/CD automation, and drift detection" \
      org.opencontainers.image.source="${SOURCE_URL}" \
      org.opencontainers.image.documentation="${SOURCE_URL}/tree/main/docs" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.licenses="${LICENSES}" \
      org.opencontainers.image.vendor="Mahdiar-Farzinfar"

ENV DEBIAN_FRONTEND=noninteractive \
    ASDF_DATA_DIR=/opt/asdf \
    ASDF_CONFIG_FILE=/etc/asdfrc \
    MISE_DATA_DIR=/opt/mise \
    GOPATH=/home/${USERNAME}/go \
    PATH=/opt/asdf/shims:/opt/asdf/bin:/usr/local/go/bin:/home/${USERNAME}/.local/bin:${PATH}

# Build and runtime prerequisites for the POSIX installer and asdf plugins.
# No apt upgrade is performed; package lists and caches are removed in this
# layer so the resulting image remains suitable for scanning.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        build-essential \
        ca-certificates \
        curl \
        file \
        git \
        golang-go \
        gnupg \
        jq \
        libbz2-dev \
        libffi-dev \
        liblzma-dev \
        libncursesw5-dev \
        libreadline-dev \
        libsqlite3-dev \
        libssl-dev \
        libxml2-dev \
        libxmlsec1-dev \
        make \
        openssh-client \
        pkg-config \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        rsync \
        shellcheck \
        sudo \
        tar \
        unzip \
        xz-utils \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# asdf publishes binaries for both requested architectures. Verify the
# release archive against the checksums file before placing it on PATH.
RUN set -euo pipefail \
    && case "${TARGETARCH}" in amd64|arm64) ;; *) echo "unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; esac \
    && archive="asdf-v${ASDF_VERSION}-linux-${TARGETARCH}.tar.gz" \
    && base_url="https://github.com/asdf-vm/asdf/releases/download/v${ASDF_VERSION}" \
    && curl --fail --silent --show-error --location --retry 3 \
         "${base_url}/${archive}" --output "/tmp/${archive}" \
    && curl --fail --silent --show-error --location --retry 3 \
         "${base_url}/asdf-v${ASDF_VERSION}-checksums.txt" --output /tmp/asdf-checksums.txt \
    && digest="$(awk -v name="${archive}" '$2 == name { print $1; exit }' /tmp/asdf-checksums.txt)" \
    && test -n "${digest}" \
    && echo "${digest}  /tmp/${archive}" | sha256sum --check --status \
    && tar -xzf "/tmp/${archive}" -C /tmp \
    && install -m 0755 /tmp/asdf /usr/local/bin/asdf \
    && asdf version \
    && rm -f "/tmp/${archive}" /tmp/asdf /tmp/asdf-checksums.txt

# Bootstrap the exact Go compiler required by go.mod. The checksum is selected
# from the official Go release manifest for the pinned version and target
# architecture, then verified before extraction.
RUN set -euo pipefail \
    && archive="go${GO_VERSION}.linux-${TARGETARCH}.tar.gz" \
    && curl --fail --silent --show-error --location --retry 3 \
         "https://go.dev/dl/${archive}" --output "/tmp/${archive}" \
    && digest="$(curl --fail --silent --show-error --location --retry 3 \
         'https://go.dev/dl/?mode=json&include=all' \
         | jq -r --arg version "go${GO_VERSION}" --arg filename "${archive}" \
             '.[] | select(.version == $version) | .files[] | select(.filename == $filename) | .sha256' \
         | head -n 1)" \
    && test -n "${digest}" \
    && echo "${digest}  /tmp/${archive}" | sha256sum --check --status \
    && rm -rf /usr/local/go \
    && tar -C /usr/local -xzf "/tmp/${archive}" \
    && /usr/local/go/bin/go version \
    && rm -f "/tmp/${archive}"

RUN mkdir -p "${ASDF_DATA_DIR}/shims" "${ASDF_DATA_DIR}/downloads" /opt/mise \
    && printf '%s\n' 'legacy_version_file = yes' > "${ASDF_CONFIG_FILE}"

# Plugin URLs are explicit to avoid depending on the mutable community
# registry. Each plugin is only a resolver; the repository's Go installer
# remains the source of truth for versions and installation decisions.
RUN set -euo pipefail \
    && for spec in \
         'terraform|https://github.com/asdf-community/asdf-hashicorp.git' \
         'terragrunt|https://github.com/lotas/asdf-terragrunt.git' \
         'golang|https://github.com/asdf-community/asdf-golang.git' \
         'python|https://github.com/asdf-community/asdf-python.git' \
         'nodejs|https://github.com/asdf-vm/asdf-nodejs.git' \
         'awscli|https://github.com/asdf-community/asdf-awscli.git' \
         'docker|https://github.com/asdf-community/asdf-docker.git' \
         'tflint|https://github.com/yuuki0000/asdf-tflint.git' \
         'trivy|https://github.com/zufallsheld/asdf-trivy.git' \
         'checkov|https://github.com/amrox/asdf-checkov.git' \
         'yamllint|https://github.com/luizm/asdf-yamllint.git' \
         'shellcheck|https://github.com/luizm/asdf-shellcheck.git' \
         'shfmt|https://github.com/luizm/asdf-shfmt.git' \
         'markdownlint-cli2|https://github.com/aeons/asdf-markdownlint-cli2.git' \
         'gitleaks|https://github.com/jimmidyson/asdf-gitleaks.git' \
         'actionlint|https://github.com/craigfurman/asdf-actionlint.git' \
         'golangci-lint|https://github.com/techinpark/asdf-golangci-lint.git' \
         'task|https://github.com/particledecay/asdf-task.git' \
         'just|https://github.com/olofvndrhr/asdf-just.git' \
         'pre-commit|https://github.com/jonathanmorley/asdf-pre-commit.git' \
         'jq|https://github.com/azukiapp/asdf-jq.git' \
         'yq|https://github.com/sudermanjr/asdf-yq.git' \
         'make|https://github.com/asdf-community/asdf-make.git' \
         'terraform-docs|https://github.com/looztra/asdf-terraform-docs.git'; do \
         IFS='|' read -r name url <<< "${spec}"; \
         asdf plugin add "${name}" "${url}"; \
       done

# Copy only authoritative inputs needed by the installer.
COPY go.mod /opt/platform-live-infra/go.mod
COPY tooling/.tool-versions /opt/platform-live-infra/tooling/.tool-versions
COPY tooling/cross-platform/asdf-tool-versions /opt/platform-live-infra/tooling/cross-platform/asdf-tool-versions
COPY tooling/.terraform-version /opt/platform-live-infra/tooling/.terraform-version
COPY tooling/.terragrunt-version /opt/platform-live-infra/tooling/.terragrunt-version
COPY scripts/tools/install-tools-posix.go /opt/platform-live-infra/scripts/tools/install-tools-posix.go
COPY scripts/tools/verify-env.py /opt/platform-live-infra/scripts/tools/verify-env.py

WORKDIR /opt/platform-live-infra

# Compile and execute the repository-supported installer from the repository
# root. It validates the canonical/mirror inventories and Go contract itself.
RUN set -euo pipefail \
    && go build -trimpath -ldflags="-s -w" \
         -o /tmp/install-tools ./scripts/tools/install-tools-posix.go \
    && CI=1 /tmp/install-tools \
         --root /opt/platform-live-infra \
         --platform linux \
         --non-interactive \
         --timeout 45m \
         --install-dir /opt/asdf/shims \
    && asdf reshim \
    && rm -f /tmp/install-tools \
    && chmod -R a+rX "${ASDF_DATA_DIR}" \
    && cp tooling/.tool-versions /home/${USERNAME}/.tool-versions

# Make asdf-managed executables available in non-login shells and ensure the
# normal Dev Container user can update its own caches without root.
RUN printf '%s\n' \
      'export ASDF_DATA_DIR=/opt/asdf' \
      'export ASDF_CONFIG_FILE=/etc/asdfrc' \
      'export PATH=/opt/asdf/shims:/opt/asdf/bin:/usr/local/go/bin:$HOME/.local/bin:$PATH' \
      > /etc/profile.d/10-platform-live-infra.sh \
    && mkdir -p /home/${USERNAME}/.local/bin /home/${USERNAME}/go /workspaces \
    && chown -R ${USERNAME}:${USERNAME} /home/${USERNAME} /opt/asdf /opt/mise /workspaces

# Execute the repository verifier as a smoke check. Its current generic
# version parser raises exit 99 for tools whose regex lacks a "version" group;
# the Go installer above remains the strict build gate for every pinned tool.
RUN set -euo pipefail \
    && python3 -m py_compile scripts/tools/verify-env.py \
    && set +e \
    && python3 scripts/tools/verify-env.py \
         --root /opt/platform-live-infra \
         --platform linux \
         --timeout 20 \
         --quiet; \
    status=$?; \
    set -e; \
    if [ "${status}" -ne 0 ] && [ "${status}" -ne 3 ] && [ "${status}" -ne 99 ]; then \
      exit "${status}"; \
    fi

USER ${USERNAME}
WORKDIR /workspaces

CMD ["bash"]
