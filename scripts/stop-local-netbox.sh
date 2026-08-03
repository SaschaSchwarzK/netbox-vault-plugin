#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-netboxvaultlocal}"

source "${REPO_ROOT}/ci/netbox-docker-common.sh"

capture_docker_artifacts
stop_stack
remove_workdir

echo "Stopped local NetBox stack for compose project '${COMPOSE_PROJECT_NAME}'."
