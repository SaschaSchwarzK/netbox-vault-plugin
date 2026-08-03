#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ARTIFACT_DIR="${REPO_ROOT}/.e2e-artifacts"
WORKDIR="${ARTIFACT_DIR}/netbox-docker"
CERTS_DIR="${WORKDIR}/azure-certs"
NETBOX_DOCKER_REPO="${NETBOX_DOCKER_REPO:-https://github.com/netbox-community/netbox-docker.git}"
NETBOX_DOCKER_REF="${NETBOX_DOCKER_REF:-release}"
NETBOX_IMAGE="${NETBOX_IMAGE:-docker.io/netboxcommunity/netbox:v4.6-5.0.2}"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-netboxvaulte2e}"
HEALTH_TIMEOUT_SECONDS="${HEALTH_TIMEOUT_SECONDS:-420}"
NETBOX_TEST_PORT="${NETBOX_TEST_PORT:-8001}"
VAULT_TEST_PORT="${VAULT_TEST_PORT:-8201}"
AZURE_TEST_PORT="${AZURE_TEST_PORT:-4998}"
GCP_TEST_PORT="${GCP_TEST_PORT:-8085}"
AWS_TEST_PORT="${AWS_TEST_PORT:-4567}"
NETBOX_TEST_ADMIN_USER="${NETBOX_TEST_ADMIN_USER:-admin}"
NETBOX_TEST_ADMIN_EMAIL="${NETBOX_TEST_ADMIN_EMAIL:-admin@example.com}"
NETBOX_TEST_ADMIN_PASSWORD="${NETBOX_TEST_ADMIN_PASSWORD:-NetboxVaultTest123!}"
VAULT_TEST_ROOT_TOKEN="${VAULT_TEST_ROOT_TOKEN:-root}"
AZURE_TEST_ACCESS_TOKEN="${AZURE_TEST_ACCESS_TOKEN:-eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJhdWQiOiJodHRwczovL3ZhdWx0LmF6dXJlLm5ldCIsImlzcyI6Imh0dHBzOi8vMTI3LjAuMC4xOjQ5OTgvZmFrZSIsInN1YiI6ImVtdWxhdG9yIiwianRpIjoiZTItdGVzdCIsImV4cCI6NDA3MDkwODgwMCwiaWF0IjoxNzg1NjgwMDAwfQ.signature}"
GCP_TEST_PROJECT_ID="${GCP_TEST_PROJECT_ID:-test-project}"
GCP_TEST_ACCESS_TOKEN="${GCP_TEST_ACCESS_TOKEN:-gcp-emulator-token}"
AWS_TEST_REGION="${AWS_TEST_REGION:-us-east-1}"
AWS_TEST_ACCESS_KEY_ID="${AWS_TEST_ACCESS_KEY_ID:-test}"
AWS_TEST_SECRET_ACCESS_KEY="${AWS_TEST_SECRET_ACCESS_KEY:-test}"
KEEP_STACK_RUNNING="${KEEP_STACK_RUNNING:-0}"
KEEP_WORKDIR="${KEEP_WORKDIR:-0}"

prepare_e2e_workspace() {
  mkdir -p "${ARTIFACT_DIR}"
  rm -rf "${WORKDIR}"
  echo "Cloning official netbox-docker (${NETBOX_DOCKER_REF})"
  git clone --depth 1 --branch "${NETBOX_DOCKER_REF}" "${NETBOX_DOCKER_REPO}" "${WORKDIR}"
  mkdir -p "${WORKDIR}/configuration" "${WORKDIR}/plugin-src"
  cp "${REPO_ROOT}/tests/e2e/stack/Dockerfile-Plugins" "${WORKDIR}/Dockerfile-Plugins"
  cp "${REPO_ROOT}/tests/e2e/stack/docker-compose.override.yml" "${WORKDIR}/docker-compose.override.yml"
  cp "${REPO_ROOT}/tests/e2e/stack/configuration/plugins.py" "${WORKDIR}/configuration/plugins.py"
  cp -R "${REPO_ROOT}/netbox_vault" "${WORKDIR}/plugin-src/"
  cp "${REPO_ROOT}/pyproject.toml" "${WORKDIR}/plugin-src/"
  cp "${REPO_ROOT}/README.md" "${WORKDIR}/plugin-src/"
  generate_azure_certs
}

generate_azure_certs() {
  mkdir -p "${CERTS_DIR}"
  openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes     -keyout "${CERTS_DIR}/emulator.key"     -out "${CERTS_DIR}/emulator.crt"     -subj "/CN=azure-keyvault"
  openssl pkcs12 -export     -out "${CERTS_DIR}/emulator.pfx"     -inkey "${CERTS_DIR}/emulator.key"     -in "${CERTS_DIR}/emulator.crt"     -passout pass:emulator
}

compose_in_workdir() {
  (
    cd "${WORKDIR}"
    export NETBOX_IMAGE COMPOSE_PROJECT_NAME NETBOX_TEST_PORT VAULT_TEST_PORT AZURE_TEST_PORT GCP_TEST_PORT AWS_TEST_PORT
    export NETBOX_TEST_ADMIN_USER NETBOX_TEST_ADMIN_EMAIL NETBOX_TEST_ADMIN_PASSWORD
    export VAULT_TEST_ROOT_TOKEN AZURE_TEST_ACCESS_TOKEN GCP_TEST_PROJECT_ID GCP_TEST_ACCESS_TOKEN
    export AWS_TEST_REGION AWS_TEST_ACCESS_KEY_ID AWS_TEST_SECRET_ACCESS_KEY
    docker compose -p "${COMPOSE_PROJECT_NAME}" "$@"
  )
}

build_plugin_image() {
  echo "Building plugin-enabled NetBox e2e image"
  compose_in_workdir build netbox
}

start_core_stack() {
  echo "Starting NetBox core e2e services"
  compose_in_workdir up -d postgres redis redis-cache vault azure-keyvault gcp-secret-manager moto-aws netbox
}

start_background_services() {
  echo "Starting NetBox background e2e services"
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

wait_for_http() {
  local url="$1"
  local label="$2"
  local allow_insecure="${3:-0}"
  local started_at now
  started_at="$(date +%s)"

  while true; do
    if [[ "${allow_insecure}" == "1" ]]; then
      if curl --silent --show-error --fail --insecure --max-time 5 "${url}" >/dev/null 2>&1; then
        return 0
      fi
    else
      if curl --silent --show-error --fail --max-time 5 "${url}" >/dev/null 2>&1; then
        return 0
      fi
    fi

    now="$(date +%s)"
    if (( now - started_at > HEALTH_TIMEOUT_SECONDS )); then
      echo "Timed out waiting for ${label} at ${url}." >&2
      return 1
    fi
    sleep 5
  done
}

wait_for_vault_ready() {
  echo "Waiting for HashiCorp Vault"
  wait_for_http "http://127.0.0.1:${VAULT_TEST_PORT}/v1/sys/health" "HashiCorp Vault"
}

wait_for_azure_ready() {
  echo "Waiting for Azure Key Vault emulator"
  local started_at now
  started_at="$(date +%s)"

  while true; do
    local status
    status="$(curl --silent --insecure --output /dev/null --write-out '%{http_code}' "https://127.0.0.1:${AZURE_TEST_PORT}/secrets/ping?api-version=7.5" -H "Authorization: Bearer ${AZURE_TEST_ACCESS_TOKEN}" || true)"
    if [[ "${status}" =~ ^(200|401|403|404)$ ]]; then
      return 0
    fi

    now="$(date +%s)"
    if (( now - started_at > HEALTH_TIMEOUT_SECONDS )); then
      echo "Timed out waiting for Azure Key Vault emulator." >&2
      return 1
    fi
    sleep 5
  done
}

wait_for_gcp_ready() {
  echo "Waiting for Google Secret Manager emulator"
  local status_url="http://127.0.0.1:${GCP_TEST_PORT}/v1/projects/${GCP_TEST_PROJECT_ID}/secrets"
  wait_for_http "${status_url}" "Google Secret Manager emulator"
}

wait_for_aws_ready() {
  echo "Waiting for LocalStack Secrets Manager"
  local started_at now
  started_at="$(date +%s)"

  while true; do
    local status
    status="$(curl --silent --output /dev/null --write-out '%{http_code}' "http://127.0.0.1:${AWS_TEST_PORT}/moto-api/" || true)"
    if [[ "${status}" =~ ^(200|404)$ ]]; then
      return 0
    fi

    now="$(date +%s)"
    if (( now - started_at > HEALTH_TIMEOUT_SECONDS )); then
      echo "Timed out waiting for Moto AWS Secrets Manager emulator." >&2
      return 1
    fi
    sleep 5
  done
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
  local started_at now health_status
  started_at="$(date +%s)"
  while true; do
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

    now="$(date +%s)"
    if (( now - started_at > HEALTH_TIMEOUT_SECONDS )); then
      echo "Timed out waiting for NetBox to become healthy." >&2
      return 1
    fi
    sleep 5
  done
}

verify_admin_login_ready() {
  echo "Verifying login page"
  curl --fail --silent --show-error "http://127.0.0.1:${NETBOX_TEST_PORT}/login/" >/dev/null
}
