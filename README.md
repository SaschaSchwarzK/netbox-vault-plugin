# NetBox Vault Plugin

`netbox_vault` is a NetBox plugin that synchronizes secrets from external vault providers into a shared encrypted cache for NetBox.

Maintainer: Sascha Schwarz <sascha@providerhoelle.de>

## Motivation

In larger NetBox deployments, custom scripts and plugins often need the same credentials repeatedly. Fetching those values from an external vault for every single execution creates unnecessary latency, extra code in each script, and rate-limit pressure on the upstream vault. A per-process memory cache does not help when NetBox is scaled across multiple app and worker containers.

This plugin solves that by keeping vault backend definitions and secret metadata in PostgreSQL while storing the encrypted cached secret value in Redis. Any NetBox app or worker container that shares the same NetBox configuration can read the same cached value.

## Supported providers

- HashiCorp Vault KV v2
- Azure Key Vault
- Google Cloud Secret Manager
- AWS Secrets Manager

## Tested NetBox versions

The automated workflow matrix currently validates the plugin against these NetBox release lines:

- `v4.4.10`
- `v4.5.10`
- `v4.6.8`

## Architecture

- Vault backends and secret metadata are stored in PostgreSQL
- Cached secret values are encrypted with a Fernet key derived from NetBox's `SECRET_KEY`
- Encrypted cached secret values are stored in Redis
- Plaintext values are fetched from the upstream vault only during refresh operations
- Upstream vault credentials are not stored in PostgreSQL
- Other plugins and custom scripts can retrieve plaintext through Python helper functions exposed by this plugin

## What it does

- Stores vault backend definitions in NetBox
- Stores tracked secret definitions in NetBox
- Refreshes secrets from the upstream vault on demand or on schedule
- Encrypts cached secret values before writing them to Redis
- Exposes reusable Python service functions for NetBox plugins and custom scripts
- Provides NetBox UI pages to create, edit, delete, and refresh vault-backed secrets
- Registers one hourly NetBox background job that scans all enabled secrets and refreshes only the ones that are due
- Optionally performs a startup cache warm-up with a Redis lock so only one container does the work

## Security model

- Plaintext is never written to PostgreSQL by the plugin runtime
- Cached secret values are encrypted with a Fernet key derived from Django/NetBox `SECRET_KEY`
- Changing `SECRET_KEY` invalidates the ability to decrypt already-cached values
- Backend access credentials are read from `PLUGINS_CONFIG` or environment-backed configuration, not from the database
- Secret metadata remains in PostgreSQL so RBAC, filtering, audit state, and refresh tracking continue to use normal NetBox models

## Installation

1. Install the plugin into the same Python environment as NetBox.
2. Add `netbox_vault` to `PLUGINS`.
3. Configure provider credentials in `PLUGINS_CONFIG`.
4. Run database migrations.
5. Ensure NetBox has Redis available for the encrypted cache.
6. Ensure at least one NetBox `rqworker` process is running so the hourly system job can execute.

Example:

```python
PLUGINS = [
    "netbox_vault",
]

PLUGINS_CONFIG = {
    "netbox_vault": {
        "backend_credentials": {
            "corp-hashicorp": {
                "token": "s.xxxxx",
                "namespace": "engineering",
            },
            "corp-azure": {
                "tenant_id": "00000000-0000-0000-0000-000000000000",
                "client_id": "11111111-1111-1111-1111-111111111111",
                "client_secret": "super-secret",
            },
            "corp-gcp": {
                "project_id": "example-project",
                "service_account_json": {"type": "service_account"},
            },
            "corp-aws": {
                "access_key_id": "AKIA...",
                "secret_access_key": "super-secret",
                "region_name": "eu-central-1",
            },
        },
        "redis_key_prefix": "netbox_vault",
        "local_secret_cache_ttl": 10,
        "local_secret_cache_maxsize": 256,
        "request_timeout": 15,
        "startup_sync_enabled": True,
    }
}
```

## Configuration notes

- `backend_credentials`: mapping of backend names or `credentials_key` aliases to provider credentials
- `redis_key_prefix`: prefix for Redis keys used by this plugin
- `redis_url`: optional explicit Redis URL; if omitted, the plugin uses NetBox's Redis cache configuration
- `local_secret_cache_ttl`: short per-process in-memory cache lifetime in seconds for repeated secret reads; default `10`
- `local_secret_cache_maxsize`: maximum number of plaintext secret entries kept in the short-lived per-process cache; default `256`
- `request_timeout`: upstream request timeout in seconds
- `startup_sync_enabled`: enable one-time startup cache warm-up logic
- `startup_sync_lock_ttl`: Redis lock TTL for startup warm-up
- `startup_sync_marker_ttl`: Redis completion marker TTL for startup warm-up

## Backend setup

### HashiCorp Vault

- `api_url`: Vault base URL such as `https://vault.example.com`
- `secret_engine`: KV v2 mount path such as `secret`
- Secret path on each cached secret: logical path inside the mount
- Secret key on each cached secret: key within the JSON payload, default `value`

### Azure Key Vault

- `api_url`: Vault URL such as `https://example.vault.azure.net`
- Secret path on each cached secret: Azure secret name
- Secret key is ignored and may be left at the default

### Google Cloud Secret Manager

- `api_url`: usually `https://secretmanager.googleapis.com`
- Credentials: `service_account_json`, `service_account_file`, or `access_token` in `PLUGINS_CONFIG`
- `project_id` is required in `PLUGINS_CONFIG` unless each secret path is a full `projects/...` resource name
- Secret path on each cached secret: either a short secret name, `secret-name/versions/latest`, `secrets/secret-name/versions/latest`, or a full resource name
- Secret key is ignored

### AWS Secrets Manager

- `api_url`: AWS endpoint override such as `https://secretsmanager.eu-central-1.amazonaws.com`
- Credentials: `access_key_id`, `secret_access_key`, optional `session_token`, and `region_name` in `PLUGINS_CONFIG`
- Secret path on each cached secret: secret name or ARN
- Secret key is ignored

## How to use

1. Create a vault backend in NetBox and reference the credentials block you configured in `PLUGINS_CONFIG`.
   Placeholder image: `docs/images/01-create-backend.png`
2. Add one or more vault secrets, set their upstream paths, and choose the refresh interval.
   Placeholder image: `docs/images/02-create-secret.png`
3. Trigger a manual refresh once to populate the encrypted Redis cache and verify the sync state.
   Placeholder image: `docs/images/03-refresh-secret.png`
4. Read cached values from your own plugin code or custom scripts using the helper functions below.
   Placeholder image: `docs/images/04-read-secret-from-code.png`

## Using secrets from code

```python
from netbox_vault.secrets import get_secret_value, set_secret_value

api_token = get_secret_value("api-token")
set_secret_value("api-token", "rotated-token-value")
```

Available helpers:

- `get_secret_value(identifier, refresh_if_due=False, allow_stale=True)`
- `get_secret_record(identifier)`
- `get_cached_secret_value(identifier)`
- `set_secret_value(identifier, value, refresh_cache=True)` updates the upstream vault and refreshes the encrypted Redis cache
- `refresh_secret(secret)`
- `refresh_all_secrets(due_only=False)`
- `refresh_due_or_missing_cache_secrets()`
- `clear_secret_cache(secret)`

Behavior notes:

- Plaintext secret values are never shown by the NetBox UI
- Plaintext secret values are never returned by the plugin API
- The `POST /api/plugins/vault/vault-secrets/<id>/set-value/` action accepts a write-only `value` field and returns secret metadata only
- Backends can be marked `read_only`; in that mode NetBox can still read and refresh secrets, but all NetBox-driven upstream write operations are blocked
- Repeated reads within one app or worker process use a short-lived in-memory cache before falling back to Redis and decryption again
- Because that optimization is per process, another container can briefly serve the previous plaintext until the local cache TTL expires; keep the TTL short if fast cross-container visibility matters

## Refresh behavior

- Each secret has a refresh interval from 1 to 24 hours
- The UI exposes ad hoc refresh for one secret and for all secrets
- Writable backends also expose a one-time set/update action in the UI and API; after a successful upstream write the encrypted Redis cache is refreshed immediately
- Read-only backends suppress the set/update UI flow and reject the API write action
- The plugin registers one hourly NetBox system job in `netbox_vault/jobs.py`
- That hourly job does not create one scheduled job per secret; it scans all enabled secrets and refreshes only those whose interval is due
- Manual refresh remains available through the management command:

```bash
python manage.py refresh_vault_secrets --due-only
```

## Local smoke test

This repository includes a Docker-based smoke test that uses the official `netbox-community/netbox-docker` stack, installs this plugin into a custom image, starts NetBox, and verifies that the app comes up with the plugin enabled.

Run it locally with:

```bash
./scripts/run-smoke-test.sh
```

Useful local options:

```bash
KEEP_STACK_RUNNING=1 KEEP_WORKDIR=1 ./scripts/run-smoke-test.sh
```

## Start NetBox locally

If you want a running local NetBox instance with the plugin installed, use:

```bash
./scripts/start-local-netbox.sh
```

Stop it with:

```bash
./scripts/stop-local-netbox.sh
```

## CI and Playwright report

The repository keeps the latest successful Playwright HTML reports from `main` under [`playwright-report/index.html`](playwright-report/index.html). The report update commit is generated only after the `main` branch e2e workflow succeeds, and that commit changes only the committed report assets so it does not retrigger the test workflows.

<object data="./playwright-report/index.html" type="text/html" width="100%" height="640">
  <p>The embedded HTML report may not render in every Markdown viewer. Open <a href="./playwright-report/index.html">playwright-report/index.html</a> directly if needed.</p>
</object>

Local Playwright output is written to `.playwright-report/` and remains ignored by Git.

## Versioning and releases

- The package version is defined once in `netbox_vault/version.py`
- Release tags must use the format `vX.Y.Z`
- The release workflow validates that the Git tag and the built package version match before publishing
- The release workflow runs the Python test suite across the supported NetBox matrix before building and publishing the package

## GitHub Actions

- Python regression suite: [.github/workflows/netbox-plugin-python-tests.yml](.github/workflows/netbox-plugin-python-tests.yml)
- Docker smoke suite: [.github/workflows/netbox-docker-smoke.yml](.github/workflows/netbox-docker-smoke.yml)
- Playwright e2e suite and report publishing: [.github/workflows/netbox-plugin-e2e.yml](.github/workflows/netbox-plugin-e2e.yml)
- Release pipeline: [.github/workflows/release.yml](.github/workflows/release.yml)

## License

This project is licensed under the Mozilla Public License 2.0. See [LICENSE](LICENSE).

Copyright (c) 2026 Sascha Schwarz <sascha@providerhoelle.de>
