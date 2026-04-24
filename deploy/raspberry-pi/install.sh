#!/usr/bin/env bash

set -euo pipefail

APP_DIR=/opt/dion_ava1
VENV_DIR="$APP_DIR/.venv"
ENV_TARGET=/etc/default/dion_ava1
ENV_EXAMPLE_REL=deploy/raspberry-pi/dion_ava1.env.example
SYSTEMD_UNIT_NAME=dion-api.service
SYSTEMD_UNIT_SOURCE_REL=deploy/raspberry-pi/dion-api.service
DATA_DIR="$APP_DIR/var"
EXPORTS_DIR="$DATA_DIR/exports"
APT_PACKAGES=(
  python3
  python3-venv
  python3-pip
  git
  curl
)

log() {
  printf '[dion-install] %s\n' "$*"
}

fail() {
  printf '[dion-install] ERROR: %s\n' "$*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    fail "run this script as root, for example with sudo"
  fi
}

verify_platform() {
  [[ -f /etc/os-release ]] || fail "/etc/os-release is missing"
  if ! grep -Eq '^ID=raspbian$|^NAME="Raspberry Pi OS"$|^PRETTY_NAME="Raspberry Pi OS' /etc/os-release; then
    fail "this installer targets clean Raspberry Pi OS only"
  fi

  local model
  model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
  if [[ "${model}" != *"Raspberry Pi 5"* ]]; then
    fail "this installer targets Raspberry Pi 5; detected model: ${model:-unknown}"
  fi
}

verify_repo_location() {
  local script_dir repo_dir
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  repo_dir="$(cd -- "${script_dir}/../.." && pwd)"
  if [[ "${repo_dir}" != "${APP_DIR}" ]]; then
    fail "expected repo at ${APP_DIR}, found ${repo_dir}"
  fi
  cd "${repo_dir}"
}

install_system_packages() {
  log "Installing Raspberry Pi OS system packages"
  apt-get update
  apt-get install -y "${APT_PACKAGES[@]}"
}

prepare_runtime_dirs() {
  log "Preparing runtime directories"
  install -d -m 755 "${APP_DIR}" "${DATA_DIR}" "${EXPORTS_DIR}"
}

create_or_refresh_venv() {
  log "Creating Python virtual environment"
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/pip" install .
}

run_migrations() {
  log "Running database migrations"
  "${VENV_DIR}/bin/python" -m app.main
}

install_env_template_if_missing() {
  local env_source="${APP_DIR}/${ENV_EXAMPLE_REL}"
  [[ -f "${env_source}" ]] || fail "missing env example: ${env_source}"

  if [[ -f "${ENV_TARGET}" ]]; then
    log "Preserving existing ${ENV_TARGET}"
    return
  fi

  log "Installing ${ENV_TARGET} from example template"
  install -m 640 "${env_source}" "${ENV_TARGET}"
}

install_systemd_unit() {
  local unit_source="${APP_DIR}/${SYSTEMD_UNIT_SOURCE_REL}"
  local unit_target="/etc/systemd/system/${SYSTEMD_UNIT_NAME}"
  [[ -f "${unit_source}" ]] || fail "missing systemd unit: ${unit_source}"

  log "Installing systemd unit ${SYSTEMD_UNIT_NAME}"
  install -m 644 "${unit_source}" "${unit_target}"
  systemctl daemon-reload
  systemctl enable --now "${SYSTEMD_UNIT_NAME}"
}

print_next_steps() {
  cat <<'EOF'

Deployment install complete.

Next steps on this Raspberry Pi OS stand:
1. Edit /etc/default/dion_ava1 for the real stand configuration.
2. Set DION_HARDWARE_PROVIDER=real when deploying the real stand.
3. Replace the placeholder drum and lock port values with verified /dev/serial/by-path/... entries.
4. Do not use ttyUSB0 or ttyUSB1 for drum or lock.
5. Verify the current USB identities:
   ls -l /dev/serial/by-path
   readlink -f /dev/serial/by-path/*
6. Restart and inspect the service:
   sudo systemctl restart dion-api.service
   sudo systemctl status dion-api.service --no-pager
   sudo journalctl -u dion-api.service -n 100 --no-pager
7. Run hardware diagnostics before handing over the stand:
   cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health
8. Sign in to /ui/admin with the current baseline credentials and change the password on first use.
EOF
}

main() {
  require_root
  verify_platform
  verify_repo_location
  install_system_packages
  prepare_runtime_dirs
  create_or_refresh_venv
  run_migrations
  install_env_template_if_missing
  install_systemd_unit
  print_next_steps
}

main "$@"
