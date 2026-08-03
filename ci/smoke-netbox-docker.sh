#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${REPO_ROOT}/ci/netbox-docker-common.sh"

cleanup() {
  local exit_code="$1"
  if [[ -d "${WORKDIR}" ]]; then
    capture_docker_artifacts || true
    if [[ "${KEEP_STACK_RUNNING}" != "1" ]]; then
      stop_stack
    fi
    if [[ "${KEEP_WORKDIR}" != "1" && "${KEEP_STACK_RUNNING}" != "1" ]]; then
      remove_workdir
    fi
  fi
  exit "${exit_code}"
}
trap 'cleanup "$?"' EXIT

prepare_netbox_docker_workspace
build_plugin_image
start_core_stack
wait_for_netbox_health
run_smoke_checks
start_background_services

echo "Smoke test passed"
