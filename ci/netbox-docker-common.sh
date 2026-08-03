#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="${REPO_ROOT}/.ci-artifacts"
WORKDIR="${ARTIFACT_DIR}/netbox-docker"
NETBOX_DOCKER_REPO="${NETBOX_DOCKER_REPO:-https://github.com/netbox-community/netbox-docker.git}"
NETBOX_DOCKER_REF="${NETBOX_DOCKER_REF:-release}"
NETBOX_IMAGE="${NETBOX_IMAGE:-docker.io/netboxcommunity/netbox:v4.6-5.0.2}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-netboxvaultci}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-360}"
KEEP_STACK_RUNNING="${KEEP_STACK_RUNNING:-0}"
KEEP_WORKDIR="${KEEP_WORKDIR:-0}"

prepare_netbox_docker_workspace() {
  mkdir -p "${ARTIFACT_DIR}"
  rm -rf "${WORKDIR}"

  echo "Cloning official netbox-docker (${NETBOX_DOCKER_REF})"
  git clone --depth 1 --branch "${NETBOX_DOCKER_REF}" "${NETBOX_DOCKER_REPO}" "${WORKDIR}"

  mkdir -p "${WORKDIR}/configuration" "${WORKDIR}/plugin-src"
  cp "${REPO_ROOT}/ci/netbox-docker/Dockerfile-Plugins" "${WORKDIR}/Dockerfile-Plugins"
  cp "${REPO_ROOT}/ci/netbox-docker/docker-compose.override.yml" "${WORKDIR}/docker-compose.override.yml"
  cp "${REPO_ROOT}/ci/netbox-docker/configuration/plugins.py" "${WORKDIR}/configuration/plugins.py"
  cp -R "${REPO_ROOT}/netbox_vault" "${WORKDIR}/plugin-src/"
  cp "${REPO_ROOT}/pyproject.toml" "${WORKDIR}/plugin-src/"
  cp "${REPO_ROOT}/README.md" "${WORKDIR}/plugin-src/"
}

compose_in_workdir() {
  (
    cd "${WORKDIR}"
    export NETBOX_IMAGE
    export COMPOSE_PROJECT_NAME
    docker compose -p "${COMPOSE_PROJECT_NAME}" "$@"
  )
}

build_plugin_image() {
  echo "Building plugin-enabled NetBox image"
  compose_in_workdir build netbox
}

start_core_stack() {
  echo "Starting NetBox core services"
  compose_in_workdir up -d postgres redis redis-cache netbox
}

start_background_services() {
  echo "Starting NetBox background services"
  compose_in_workdir up -d netbox-worker netbox-housekeeping
}

capture_docker_artifacts() {
  if [[ -d "${WORKDIR}" ]]; then
    compose_in_workdir ps > "${ARTIFACT_DIR}/docker-compose-ps.txt" 2>&1 || true
    compose_in_workdir logs --no-color > "${ARTIFACT_DIR}/docker-compose.log" 2>&1 || true
  fi
}

stop_stack() {
  if [[ -d "${WORKDIR}" ]]; then
    compose_in_workdir down -v --remove-orphans > "${ARTIFACT_DIR}/docker-compose-down.txt" 2>&1 || true
  fi
}

remove_workdir() {
  if [[ -d "${WORKDIR}" ]]; then
    rm -rf "${WORKDIR}"
  fi
}

get_netbox_container_id() {
  compose_in_workdir ps -q netbox
}

wait_for_netbox_health() {
  local container_id
  container_id="$(get_netbox_container_id)"
  if [[ -z "${container_id}" ]]; then
    echo "NetBox container did not start." >&2
    return 1
  fi

  echo "Waiting for NetBox healthcheck"
  local started_at
  started_at="$(date +%s)"
  while true; do
    local health_status
    health_status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "${container_id}")"
    case "${health_status}" in
      healthy)
        return 0
        ;;
      exited|dead)
        echo "NetBox container entered state '${health_status}'." >&2
        return 1
        ;;
    esac

    local now
    now="$(date +%s)"
    if (( now - started_at > HEALTH_TIMEOUT_SECONDS )); then
      echo "Timed out waiting for NetBox to become healthy." >&2
      return 1
    fi

    sleep 5
  done
}

run_smoke_checks() {
  echo "Checking login page"
  curl --fail --silent --show-error http://127.0.0.1:8000/login/ > /dev/null

  echo "Checking plugin registration"
  compose_in_workdir exec -T netbox \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py shell -c \
    "from django.conf import settings; assert 'netbox_vault' in settings.PLUGINS"

  echo "Checking plugin migrations"
  compose_in_workdir exec -T netbox \
    /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py showmigrations netbox_vault
}
