#!/usr/bin/env bash
# shellcheck shell=bash
#
# Thin POSIX wrapper for scripts/cross-platform/setup.py.
# All repository/toolchain business logic remains in setup.py.

if [[ -z "${BASH_VERSION:-}" ]]; then
  if command -v bash >/dev/null 2>&1; then
    exec bash "$0" "$@"
  fi
  printf '[cross-platform:setup.sh][ERROR] bash is required but was not found in PATH.\n' >&2
  exit 2
fi

set -Eeuo pipefail
IFS=$'\n\t'

readonly WRAPPER_NAME='cross-platform:setup.sh'
readonly WRAPPER_KIND='bash'
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
ROOT_DIR="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
readonly ROOT_DIR
readonly SETUP_PY="${SCRIPT_DIR}/setup.py"
readonly TOOL_VERSIONS_FILE="${ROOT_DIR}/tooling/.tool-versions"

log() {
  printf '[%s] %s\n' "${WRAPPER_NAME}" "$*" >&2
}

err() {
  printf '[%s][ERROR] %s\n' "${WRAPPER_NAME}" "$*" >&2
}

unexpected_error() {
  local status=$?
  err "unexpected command failure at shell line ${BASH_LINENO[0]:-unknown} (exit ${status})"
  exit "${status}"
}

trap unexpected_error ERR

DRY_RUN=0
NON_INTERACTIVE=0
for arg in "$@"; do
  case "${arg}" in
  --dry-run)
    DRY_RUN=1
    ;;
  --non-interactive)
    NON_INTERACTIVE=1
    ;;
  esac
done
if [[ -n "${CI:-}" ]]; then
  NON_INTERACTIVE=1
fi

if [[ ! -f "${SETUP_PY}" ]]; then
  err "Source-of-truth script not found: ${SETUP_PY}"
  exit 2
fi
if [[ ! -r "${TOOL_VERSIONS_FILE}" ]]; then
  err "Tool versions file not found or unreadable: ${TOOL_VERSIONS_FILE}"
  exit 2
fi

RAW_OS="$(uname -s 2>/dev/null || true)"
RAW_ARCH="$(uname -m 2>/dev/null || true)"
KERNEL="$(uname -r 2>/dev/null || true)"
if [[ -z "${RAW_OS}" ]]; then
  err 'Unable to determine the host operating system with uname.'
  exit 4
fi

case "${RAW_OS}" in
Linux*)
  PLATFORM='linux'
  ;;
Darwin*)
  PLATFORM='macos'
  ;;
CYGWIN* | MINGW* | MSYS*)
  PLATFORM='windows'
  ;;
*)
  err "Unsupported host operating system: ${RAW_OS}"
  exit 4
  ;;
esac

case "${RAW_ARCH}" in
x86_64 | amd64)
  ARCH='x86_64'
  ;;
aarch64 | arm64)
  ARCH='arm64'
  ;;
i386 | i686)
  ARCH='x86'
  ;;
*)
  ARCH="${RAW_ARCH:-unknown}"
  ;;
esac

WSL='0'
case "${KERNEL}" in
*microsoft* | *Microsoft* | *wsl* | *WSL*)
  WSL='1'
  ;;
esac

export BOOTSTRAP_WRAPPER_KIND="${WRAPPER_KIND}"
export BOOTSTRAP_WRAPPER_OS="${PLATFORM}"
export BOOTSTRAP_WRAPPER_OS_RAW="${RAW_OS}"
export BOOTSTRAP_WRAPPER_ARCH="${ARCH}"
export BOOTSTRAP_WRAPPER_DISTRO=''
export BOOTSTRAP_WRAPPER_KERNEL="${KERNEL:-unknown}"
export BOOTSTRAP_WRAPPER_WSL="${WSL}"
export CROSS_PLATFORM_PLATFORM="${PLATFORM}"

log "Host environment: os=${PLATFORM} arch=${ARCH} wsl=${WSL} kernel=${KERNEL:-unknown}"

read_required_python_version() {
  local parsed
  if ! parsed="$(
    awk '
      function trim(value) {
        sub(/^[[:space:]]+/, "", value)
        sub(/[[:space:]]+$/, "", value)
        return value
      }
      {
        line = $0
        sub(/[[:space:]]*#.*/, "", line)
        line = trim(line)
        if (line == "") {
          next
        }

        field_count = split(line, fields, /[[:space:]]+/)
        if (field_count != 2) {
          print "malformed entry at line " NR ": expected '\''<tool> <version>'\''"
          invalid = 1
          next
        }

        if (fields[1] == "python") {
          python_count++
          if (python_count > 1) {
            print "duplicate python entries found (line " NR ")"
            invalid = 1
          } else {
            python_version = fields[2]
          }
        }
      }
      END {
        if (python_count == 0) {
          print "no '\''python <version>'\'' entry found"
          exit 3
        }
        if (python_version !~ /^[0-9]+\.[0-9]+(\.[0-9]+)?$/) {
          print "python version is not a concrete numeric pin: " python_version
          exit 2
        }
        if (invalid) {
          exit 2
        }
        print python_version
      }
    ' "${TOOL_VERSIONS_FILE}"
  )"; then
    err "${parsed:-failed to parse ${TOOL_VERSIONS_FILE}}"
    return 1
  fi

  if [[ ! "${parsed}" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
    err "Invalid Python version pin in ${TOOL_VERSIONS_FILE}: ${parsed}"
    return 1
  fi
  printf '%s\n' "${parsed}"
}

if ! REQUIRED_PY_VERSION="$(read_required_python_version)"; then
  exit 2
fi
log "Required Python version: ${REQUIRED_PY_VERSION}"

version_ge() {
  local -a actual required
  local index actual_part required_part
  IFS='.' read -r -a actual <<<"$1"
  IFS='.' read -r -a required <<<"$2"

  for index in 0 1 2; do
    actual_part="${actual[index]:-0}"
    required_part="${required[index]:-0}"
    if ((10#${actual_part} > 10#${required_part})); then
      return 0
    fi
    if ((10#${actual_part} < 10#${required_part})); then
      return 1
    fi
  done
  return 0
}

interpreter_version() {
  local interpreter="$1"
  local version
  if ! version="$(
    "${interpreter}" -c \
      'import sys; print(".".join(map(str, sys.version_info[:3])))' \
      2>/dev/null
  )"; then
    return 1
  fi
  if [[ ! "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    return 1
  fi
  printf '%s\n' "${version}"
}

PYTHON_BIN=''
PYTHON_VERSION=''

find_suitable_python() {
  local candidate resolved version
  for candidate in python3 python; do
    if ! resolved="$(command -v "${candidate}" 2>/dev/null)"; then
      continue
    fi
    if [[ "${resolved}" != */* || ! -x "${resolved}" ]]; then
      log "Skipping ${candidate}: command does not resolve to an executable path."
      continue
    fi
    if ! version="$(interpreter_version "${resolved}")"; then
      log "Skipping ${resolved}: unable to query its Python version."
      continue
    fi
    if version_ge "${version}" "${REQUIRED_PY_VERSION}"; then
      PYTHON_BIN="${resolved}"
      PYTHON_VERSION="${version}"
      return 0
    fi
    log "Skipping ${resolved} (Python ${version}); requires >= ${REQUIRED_PY_VERSION}."
  done
  return 1
}

set_python_candidate() {
  local candidate="$1"
  if [[ ! -x "${candidate}" ]]; then
    return 1
  fi
  local version
  if ! version="$(interpreter_version "${candidate}")"; then
    return 1
  fi
  if ! version_ge "${version}" "${REQUIRED_PY_VERSION}"; then
    err "Candidate ${candidate} provides Python ${version}; requires >= ${REQUIRED_PY_VERSION}."
    return 1
  fi
  PYTHON_BIN="${candidate}"
  PYTHON_VERSION="${version}"
  return 0
}

install_with_mise() {
  local prefix candidate
  if ! command -v mise >/dev/null 2>&1; then
    return 1
  fi
  log "Installing Python ${REQUIRED_PY_VERSION} via mise."
  if ! MISE_YES=1 mise install "python@${REQUIRED_PY_VERSION}"; then
    err 'mise failed to install the required Python version.'
    return 1
  fi
  if ! prefix="$(mise where "python@${REQUIRED_PY_VERSION}")"; then
    err 'mise installed Python but did not return its installation path.'
    return 1
  fi
  for candidate in "${prefix}/bin/python3" "${prefix}/bin/python"; do
    if set_python_candidate "${candidate}"; then
      return 0
    fi
  done
  err "Unable to resolve the Python executable installed by mise at ${prefix}."
  return 1
}

install_with_asdf() {
  local plugins prefix candidate
  if ! command -v asdf >/dev/null 2>&1; then
    return 1
  fi
  log "Installing Python ${REQUIRED_PY_VERSION} via asdf."
  if plugins="$(asdf plugin list 2>/dev/null)"; then
    if ! grep -qx 'python' <<<"${plugins}"; then
      if ! asdf plugin add python; then
        err 'asdf could not add the python plugin.'
        return 1
      fi
    fi
  else
    if ! asdf plugin add python; then
      err 'asdf could not list or add the python plugin.'
      return 1
    fi
  fi
  if ! asdf install python "${REQUIRED_PY_VERSION}"; then
    err 'asdf failed to install the required Python version.'
    return 1
  fi
  if ! prefix="$(asdf where python "${REQUIRED_PY_VERSION}")"; then
    err 'asdf installed Python but did not return its installation path.'
    return 1
  fi
  for candidate in "${prefix}/bin/python3" "${prefix}/bin/python"; do
    if set_python_candidate "${candidate}"; then
      return 0
    fi
  done
  err "Unable to resolve the Python executable installed by asdf at ${prefix}."
  return 1
}

install_with_pyenv() {
  local pyenv_root candidate
  if ! command -v pyenv >/dev/null 2>&1; then
    return 1
  fi
  log "Installing Python ${REQUIRED_PY_VERSION} via pyenv."
  if ! pyenv install --skip-existing "${REQUIRED_PY_VERSION}"; then
    err 'pyenv failed to install the required Python version.'
    return 1
  fi
  if ! pyenv_root="$(pyenv root)"; then
    err 'pyenv did not return its root directory.'
    return 1
  fi
  for candidate in \
    "${pyenv_root}/versions/${REQUIRED_PY_VERSION}/bin/python3" \
    "${pyenv_root}/versions/${REQUIRED_PY_VERSION}/bin/python"; do
    if set_python_candidate "${candidate}"; then
      return 0
    fi
  done
  err "Unable to resolve the Python executable installed by pyenv at ${pyenv_root}."
  return 1
}

sudo_prefix() {
  if [[ "$(id -u)" -eq 0 ]]; then
    return 0
  fi
  if ! command -v sudo >/dev/null 2>&1; then
    err 'Root privileges or sudo are required for the selected system package manager.'
    return 1
  fi
  if [[ "${NON_INTERACTIVE}" -eq 1 ]]; then
    sudo -n true
  else
    sudo -v
  fi
}

install_with_package_manager() {
  local major_minor package
  major_minor="$(printf '%s\n' "${REQUIRED_PY_VERSION}" | awk -F. '{print $1 "." $2}')"

  case "${PLATFORM}" in
  macos)
    if ! command -v brew >/dev/null 2>&1; then
      err "Homebrew is not available; install Python ${REQUIRED_PY_VERSION} with mise, asdf, or pyenv."
      return 1
    fi
    package="python@${major_minor}"
    log "Installing ${package} via Homebrew (the resulting patch version will be verified)."
    if ! HOMEBREW_NO_AUTO_UPDATE=1 brew install "${package}"; then
      err "Homebrew failed to install ${package}."
      return 1
    fi
    ;;
  linux)
    if command -v apt-get >/dev/null 2>&1; then
      package="python${major_minor}"
      if ! sudo_prefix; then
        return 1
      fi
      log "Installing ${package} via apt-get."
      if [[ "$(id -u)" -eq 0 ]]; then
        if ! DEBIAN_FRONTEND=noninteractive apt-get install -y "${package}"; then
          err "apt-get failed to install ${package}."
          return 1
        fi
      elif [[ "${NON_INTERACTIVE}" -eq 1 ]]; then
        if ! sudo -n env DEBIAN_FRONTEND=noninteractive apt-get install -y "${package}"; then
          err "apt-get failed to install ${package}."
          return 1
        fi
      else
        if ! sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y "${package}"; then
          err "apt-get failed to install ${package}."
          return 1
        fi
      fi
    elif command -v dnf >/dev/null 2>&1; then
      package="python${major_minor}"
      if ! sudo_prefix; then
        return 1
      fi
      log "Installing ${package} via dnf."
      if [[ "$(id -u)" -eq 0 ]]; then
        if ! dnf install -y "${package}"; then
          err "dnf failed to install ${package}."
          return 1
        fi
      elif [[ "${NON_INTERACTIVE}" -eq 1 ]]; then
        if ! sudo -n dnf install -y "${package}"; then
          err "dnf failed to install ${package}."
          return 1
        fi
      else
        if ! sudo dnf install -y "${package}"; then
          err "dnf failed to install ${package}."
          return 1
        fi
      fi
    else
      err 'No supported Linux package manager found (apt-get or dnf).'
      return 1
    fi
    ;;
  *)
    err "No safe package-manager fallback is defined for platform ${PLATFORM}."
    return 1
    ;;
  esac

  if find_suitable_python; then
    return 0
  fi
  err "Python installation completed, but no interpreter satisfying >= ${REQUIRED_PY_VERSION} was found."
  return 1
}

install_python() {
  if install_with_mise; then
    return 0
  fi
  if install_with_asdf; then
    return 0
  fi
  if install_with_pyenv; then
    return 0
  fi
  install_with_package_manager
}

if ! find_suitable_python; then
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "DRY-RUN: no suitable Python is available; no installation or network activity will be attempted."
    log "DRY-RUN: a supported version manager (mise/asdf/pyenv) or platform package manager would be used for Python ${REQUIRED_PY_VERSION}."
    err "Dry-run cannot invoke setup.py without a usable Python interpreter. Install Python ${REQUIRED_PY_VERSION} or rerun without --dry-run."
    exit 2
  fi
  log "No suitable Python interpreter found; attempting supported bootstrap methods."
  if ! install_python; then
    err "Unable to provision Python ${REQUIRED_PY_VERSION}."
    err 'Install the pinned Python version with mise, asdf, or pyenv, then rerun this wrapper.'
    exit 2
  fi
fi

if [[ -z "${PYTHON_BIN}" || ! -x "${PYTHON_BIN}" ]]; then
  err 'Resolved Python interpreter is missing or not executable.'
  exit 2
fi
if ! PYTHON_VERSION="$(interpreter_version "${PYTHON_BIN}")"; then
  err "Unable to determine the Python version for ${PYTHON_BIN}."
  exit 2
fi
if ! version_ge "${PYTHON_VERSION}" "${REQUIRED_PY_VERSION}"; then
  err "Resolved Python ${PYTHON_VERSION} does not satisfy required >= ${REQUIRED_PY_VERSION}."
  exit 2
fi

log "Using Python: ${PYTHON_BIN} (Python ${PYTHON_VERSION})"
log "Delegating to SoT: ${SETUP_PY}"

# Keep the caller's working directory and argv unchanged. setup.py resolves
# repository-relative paths from its own location and receives platform context
# through environment variables rather than an injected/reordered argument.
exec "${PYTHON_BIN}" "${SETUP_PY}" "$@"
