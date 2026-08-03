from os import environ

plugin_config = {
    "backend_credentials": {
        "hashicorp-test": {
            "token": environ.get("VAULT_TEST_ROOT_TOKEN", "root"),
        },
        "azure-test": {
            "access_token": environ.get("AZURE_TEST_ACCESS_TOKEN", "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJhdWQiOiJodHRwczovL3ZhdWx0LmF6dXJlLm5ldCIsImlzcyI6Imh0dHBzOi8vMTI3LjAuMC4xOjQ5OTgvZmFrZSIsInN1YiI6ImVtdWxhdG9yIiwianRpIjoiZTItdGVzdCIsImV4cCI6NDA3MDkwODgwMCwiaWF0IjoxNzg1NjgwMDAwfQ.signature"),
            "verify_tls": False,
        },
        "gcp-test": {
            "access_token": environ.get("GCP_TEST_ACCESS_TOKEN", "gcp-emulator-token"),
            "project_id": environ.get("GCP_TEST_PROJECT_ID", "test-project"),
        },
        "aws-test": {
            "access_key_id": environ.get("AWS_TEST_ACCESS_KEY_ID", "test"),
            "secret_access_key": environ.get("AWS_TEST_SECRET_ACCESS_KEY", "test"),
            "region_name": environ.get("AWS_TEST_REGION", "us-east-1"),
        },
    },
    "redis_key_prefix": environ.get("NETBOX_VAULT_REDIS_KEY_PREFIX", "netbox_vault_test"),
    "request_timeout": 10,
    "startup_sync_enabled": environ.get("NETBOX_VAULT_STARTUP_SYNC_ENABLED", "false").lower() == "true",
}

redis_url = environ.get("NETBOX_VAULT_REDIS_URL")
if redis_url:
    plugin_config["redis_url"] = redis_url

PLUGINS = ["netbox_vault"]
PLUGINS_CONFIG = {"netbox_vault": plugin_config}
