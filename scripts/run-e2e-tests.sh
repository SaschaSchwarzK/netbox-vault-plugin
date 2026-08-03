#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${REPO_ROOT}/tests/e2e/stack/common.sh"

cleanup() {
  local exit_code="$1"
  capture_docker_artifacts || true
  if [[ "${KEEP_STACK_RUNNING}" != "1" ]]; then
    stop_stack
  fi
  if [[ "${KEEP_WORKDIR}" != "1" && "${KEEP_STACK_RUNNING}" != "1" ]]; then
    remove_workdir
  fi
  exit "${exit_code}"
}
trap 'cleanup "$?"' EXIT

prepare_e2e_workspace
build_plugin_image
start_core_stack
wait_for_vault_ready
wait_for_azure_ready
wait_for_netbox_health
verify_admin_login_ready
start_background_services

npm install
npx playwright install chromium
npx playwright test
