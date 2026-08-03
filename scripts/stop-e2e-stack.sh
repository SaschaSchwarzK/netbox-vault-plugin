#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "${REPO_ROOT}/tests/e2e/stack/common.sh"

capture_docker_artifacts
stop_stack
remove_workdir

echo "Stopped NetBox e2e stack for compose project '${COMPOSE_PROJECT_NAME}'."
