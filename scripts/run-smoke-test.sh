#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cat <<CONFIG
Running local NetBox Docker smoke test with:
  NETBOX_DOCKER_REF=${NETBOX_DOCKER_REF:-release}
  NETBOX_IMAGE=${NETBOX_IMAGE:-docker.io/netboxcommunity/netbox:v4.6-5.0.2}
  COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-netboxvaultlocal}
  HEALTH_TIMEOUT_SECONDS=${HEALTH_TIMEOUT_SECONDS:-360}
  KEEP_STACK_RUNNING=${KEEP_STACK_RUNNING:-0}
  KEEP_WORKDIR=${KEEP_WORKDIR:-0}
CONFIG

COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-netboxvaultlocal}" \
"${REPO_ROOT}/ci/smoke-netbox-docker.sh"
