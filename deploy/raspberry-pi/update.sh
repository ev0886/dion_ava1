#!/usr/bin/env bash

set -euo pipefail

APP_DIR=/opt/dion_ava1
VENV_DIR="$APP_DIR/.venv"
ENV_TARGET=/etc/default/dion_ava1
SYSTEMD_UNIT_NAME=dion-api.service
SYSTEMD_UNIT_SOURCE_REL=deploy/raspberry-pi/dion-api.service

log() {
  printf '[dion-update] %s\n' "$*"
}

fail() {
  printf '[dion-update] ERROR: %s\n' "$*" >&2
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
    fail "this updater targets Raspberry Pi OS only"
  fi

  local model
  model="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || true)"
  if [[ "${model}" != *"Raspberry Pi 5"* ]]; then
    fail "this updater targets Raspberry Pi 5; detected model: ${model:-unknown}"
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

verify_existing_runtime() {
  [[ -d "${APP_DIR}" ]] || fail "missing app directory ${APP_DIR}"
  [[ -f "${ENV_TARGET}" ]] || log "warning: ${ENV_TARGET} is missing; service may still use built-in defaults"
}

refresh_venv_and_deps() {
  log "Refreshing Python virtual environment"
  python3 -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/pip" install .
}

run_migrations() {
  log "Running database migrations"
  "${VENV_DIR}/bin/python" -m app.main
}

install_systemd_unit() {
  local unit_source="${APP_DIR}/${SYSTEMD_UNIT_SOURCE_REL}"
  local unit_target="/etc/systemd/system/${SYSTEMD_UNIT_NAME}"
  [[ -f "${unit_source}" ]] || fail "missing systemd unit: ${unit_source}"

  log "Refreshing systemd unit ${SYSTEMD_UNIT_NAME}"
  install -m 644 "${unit_source}" "${unit_target}"
  systemctl daemon-reload
}

restart_service() {
  log "Restarting ${SYSTEMD_UNIT_NAME}"
  systemctl restart "${SYSTEMD_UNIT_NAME}"
  systemctl enable "${SYSTEMD_UNIT_NAME}"
}

print_next_steps() {
  cat <<'EOF'

Deployment update complete.

Local runtime configuration was preserved:
- /etc/default/dion_ava1 was not overwritten

Post-update checks:
1. sudo systemctl status dion-api.service --no-pager
2. sudo journalctl -u dion-api.service -n 100 --no-pager
3. curl -fsS http://127.0.0.1:8000/health
4. cd /opt/dion_ava1 && .venv/bin/python -m app.cli hardware-health

If this machine is a cloned or newly wired stand, verify drum and lock by-path assignments in /etc/default/dion_ava1 before using the stand.
EOF
}

main() {
  require_root
  verify_platform
  verify_repo_location
  verify_existing_runtime
  refresh_venv_and_deps
  run_migrations
  install_systemd_unit
  restart_service
  print_next_steps
}

main "$@"
