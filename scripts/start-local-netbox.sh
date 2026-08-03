#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cat <<CONFIG
Starting local NetBox with the vault plugin using:
  NETBOX_DOCKER_REF=${NETBOX_DOCKER_REF:-release}
  NETBOX_IMAGE=${NETBOX_IMAGE:-docker.io/netboxcommunity/netbox:v4.6-5.0.2}
  COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-netboxvaultlocal}
  HEALTH_TIMEOUT_SECONDS=${HEALTH_TIMEOUT_SECONDS:-360}
CONFIG

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-netboxvaultlocal}"
export KEEP_STACK_RUNNING=1
export KEEP_WORKDIR=1

source "${REPO_ROOT}/ci/netbox-docker-common.sh"

prepare_netbox_docker_workspace
build_plugin_image
start_core_stack
wait_for_netbox_health
start_background_services

cat <<DONE
NetBox is running with the plugin enabled.
  URL: http://127.0.0.1:8000/
  Workdir: ${WORKDIR}
  Compose project: ${COMPOSE_PROJECT_NAME}

To stop it again:
  ./scripts/stop-local-netbox.sh
DONE
