#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${REPO_ROOT}/tests/e2e/stack/common.sh"

export KEEP_STACK_RUNNING=1
export KEEP_WORKDIR=1

prepare_e2e_workspace
build_plugin_image
start_core_stack
wait_for_vault_ready
wait_for_azure_ready
wait_for_netbox_health
verify_admin_login_ready
start_background_services

cat <<DONE
NetBox e2e stack is running.
  NetBox: http://127.0.0.1:${NETBOX_TEST_PORT}/
  HashiCorp Vault: http://127.0.0.1:${VAULT_TEST_PORT}/
  Azure Key Vault emulator: https://127.0.0.1:${AZURE_TEST_PORT}/
  Compose project: ${COMPOSE_PROJECT_NAME}
  Workdir: ${WORKDIR}
DONE
