from __future__ import annotations

from base64 import b64decode
from dataclasses import dataclass
import json
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account
import requests
from netbox.plugins import get_plugin_config

from .models import VaultBackend, VaultBackendTypeChoices, VaultSecret


class BackendConfigurationError(ValueError):
    pass


class SecretRefreshError(RuntimeError):
    pass


def _plugin_setting(name, default=None):
    try:
        return get_plugin_config("netbox_vault", name)
    except Exception:
        return default


def _get_backend_credentials(backend: VaultBackend):
    credentials = _plugin_setting("backend_credentials", {}) or {}
    if backend.name in credentials:
        return credentials[backend.name]

    extra_config = _get_extra_config(backend)
    credential_key = extra_config.get("credentials_key")
    if credential_key and credential_key in credentials:
        return credentials[credential_key]

    return {}


def _get_extra_config(backend: VaultBackend):
    return backend.extra_config if isinstance(backend.extra_config, dict) else {}


def _get_backend_config_value(backend: VaultBackend, key: str, default=None):
    credentials = _get_backend_credentials(backend)
    if key in credentials:
        return credentials[key]
    extra_config = _get_extra_config(backend)
    if key in extra_config:
        return extra_config[key]
    return default


def _get_request_verify(backend: VaultBackend):
    verify_tls = _get_backend_config_value(backend, "verify_tls")
    if verify_tls is None:
        return True
    return verify_tls


@dataclass
class BaseVaultClient:
    backend: VaultBackend

    @property
    def timeout(self):
        return _plugin_setting("request_timeout", 15)

    @property
    def request_verify(self):
        return _get_request_verify(self.backend)

    def fetch_secret(self, secret: VaultSecret) -> str:
        raise NotImplementedError


class HashiCorpVaultClient(BaseVaultClient):
    def fetch_secret(self, secret: VaultSecret) -> str:
        token = _get_backend_config_value(self.backend, "token")
        if not token:
            raise BackendConfigurationError(
                f"Missing HashiCorp token for backend '{self.backend.name}' in PLUGINS_CONFIG."
            )

        engine = self.backend.secret_engine or "secret"
        path = secret.secret_path.strip("/")
        url = f"{self.backend.api_url.rstrip('/')}/v1/{engine}/data/{path}"
        headers = {"X-Vault-Token": token}

        namespace = _get_backend_config_value(self.backend, "namespace") or self.backend.default_namespace
        if namespace:
            headers["X-Vault-Namespace"] = namespace

        response = requests.get(url, headers=headers, timeout=self.timeout, verify=self.request_verify)
        if response.status_code >= 400:
            raise SecretRefreshError(
                f"HashiCorp Vault request failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        try:
            data = payload["data"]["data"]
            return str(data[secret.secret_key])
        except KeyError as exc:
            raise SecretRefreshError(
                f"HashiCorp Vault payload at '{secret.secret_path}' does not contain key '{secret.secret_key}'."
            ) from exc


class AzureKeyVaultClient(BaseVaultClient):
    def _get_access_token(self) -> str:
        static_access_token = _get_backend_config_value(self.backend, "access_token")
        if static_access_token:
            return static_access_token

        tenant_id = _get_backend_config_value(self.backend, "tenant_id")
        client_id = _get_backend_config_value(self.backend, "client_id")
        client_secret = _get_backend_config_value(self.backend, "client_secret")
        if not all([tenant_id, client_id, client_secret]):
            raise BackendConfigurationError(
                f"Missing Azure credentials for backend '{self.backend.name}' in PLUGINS_CONFIG."
            )

        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        response = requests.post(
            token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "https://vault.azure.net/.default",
            },
            timeout=self.timeout,
            verify=self.request_verify,
        )
        if response.status_code >= 400:
            raise SecretRefreshError(
                f"Azure token request failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise SecretRefreshError("Azure token response did not include an access token.")
        return token

    def fetch_secret(self, secret: VaultSecret) -> str:
        token = self._get_access_token()
        api_version = self.backend.azure_api_version or "7.5"
        url = f"{self.backend.api_url.rstrip('/')}/secrets/{secret.secret_path}?api-version={api_version}"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
            verify=self.request_verify,
        )
        if response.status_code >= 400:
            raise SecretRefreshError(
                f"Azure Key Vault request failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        value = payload.get("value")
        if value is None:
            raise SecretRefreshError(
                f"Azure Key Vault response for secret '{secret.secret_path}' did not include a value."
            )
        return str(value)


class GoogleCloudSecretManagerClient(BaseVaultClient):
    google_scope = "https://www.googleapis.com/auth/cloud-platform"

    def _get_access_token(self) -> str:
        static_access_token = _get_backend_config_value(self.backend, "access_token")
        if static_access_token:
            return static_access_token

        credentials_json = _get_backend_config_value(self.backend, "service_account_json")
        credentials_file = _get_backend_config_value(self.backend, "service_account_file")
        if not credentials_json and not credentials_file:
            raise BackendConfigurationError(
                f"Missing Google Cloud credentials for backend '{self.backend.name}' in PLUGINS_CONFIG."
            )

        if credentials_json:
            if isinstance(credentials_json, str):
                credentials_json = json.loads(credentials_json)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_json,
                scopes=[self.google_scope],
            )
        else:
            credentials = service_account.Credentials.from_service_account_file(
                credentials_file,
                scopes=[self.google_scope],
            )

        credentials.refresh(GoogleAuthRequest())
        if not credentials.token:
            raise SecretRefreshError("Google Cloud credentials did not yield an access token.")
        return credentials.token

    def _get_project_id(self) -> str | None:
        project_id = _get_backend_config_value(self.backend, "project_id")
        if project_id:
            return project_id

        credentials_json = _get_backend_config_value(self.backend, "service_account_json")
        if isinstance(credentials_json, str):
            credentials_json = json.loads(credentials_json)
        if isinstance(credentials_json, dict):
            return credentials_json.get("project_id")
        return None

    def _build_secret_resource(self, secret: VaultSecret) -> str:
        path = secret.secret_path.strip("/")
        if path.startswith("projects/"):
            return path

        project_id = self._get_project_id()
        if not project_id:
            raise BackendConfigurationError(
                f"Google Cloud backend '{self.backend.name}' requires a project_id when secret_path is not a full resource name."
            )

        if path.startswith("secrets/"):
            return f"projects/{project_id}/{path}"
        if "/versions/" in path:
            return f"projects/{project_id}/secrets/{path}"
        return f"projects/{project_id}/secrets/{path}/versions/latest"

    def fetch_secret(self, secret: VaultSecret) -> str:
        token = self._get_access_token()
        resource = self._build_secret_resource(secret)
        url = f"{self.backend.api_url.rstrip('/')}/v1/{resource}:access"
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.timeout,
            verify=self.request_verify,
        )
        if response.status_code >= 400:
            raise SecretRefreshError(
                f"Google Cloud Secret Manager request failed with status {response.status_code}: {response.text}"
            )

        payload = response.json()
        encoded_value = payload.get("payload", {}).get("data")
        if not encoded_value:
            raise SecretRefreshError(
                f"Google Cloud Secret Manager response for secret '{secret.secret_path}' did not include payload data."
            )
        return b64decode(encoded_value).decode("utf-8")


class AWSSecretsManagerClient(BaseVaultClient):
    def _get_region_name(self) -> str:
        region_name = _get_backend_config_value(self.backend, "region_name")
        if region_name:
            return region_name

        hostname = urlparse(self.backend.api_url).hostname or ""
        if hostname.startswith("secretsmanager."):
            parts = hostname.split('.')
            if len(parts) >= 2:
                return parts[1]

        raise BackendConfigurationError(
            f"Missing AWS region_name for backend '{self.backend.name}' in PLUGINS_CONFIG or endpoint URL."
        )

    def fetch_secret(self, secret: VaultSecret) -> str:
        access_key_id = _get_backend_config_value(self.backend, "access_key_id")
        secret_access_key = _get_backend_config_value(self.backend, "secret_access_key")
        if not access_key_id or not secret_access_key:
            raise BackendConfigurationError(
                f"Missing AWS access_key_id or secret_access_key for backend '{self.backend.name}' in PLUGINS_CONFIG."
            )

        session = boto3.session.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            aws_session_token=_get_backend_config_value(self.backend, "session_token"),
            region_name=self._get_region_name(),
        )
        client = session.client(
            "secretsmanager",
            endpoint_url=self.backend.api_url.rstrip('/'),
            verify=self.request_verify,
        )

        try:
            payload = client.get_secret_value(SecretId=secret.secret_path)
        except (BotoCoreError, ClientError) as exc:
            raise SecretRefreshError(f"AWS Secrets Manager request failed: {exc}") from exc

        if payload.get("SecretString") is not None:
            return str(payload["SecretString"])

        binary_value = payload.get("SecretBinary")
        if binary_value is None:
            raise SecretRefreshError(
                f"AWS Secrets Manager response for secret '{secret.secret_path}' did not include a secret value."
            )
        if isinstance(binary_value, bytes):
            return binary_value.decode("utf-8")
        return b64decode(binary_value).decode("utf-8")


def get_vault_client(backend: VaultBackend) -> BaseVaultClient:
    if backend.backend_type == VaultBackendTypeChoices.HASHICORP:
        return HashiCorpVaultClient(backend)
    if backend.backend_type == VaultBackendTypeChoices.AZURE_KEY_VAULT:
        return AzureKeyVaultClient(backend)
    if backend.backend_type == VaultBackendTypeChoices.GOOGLE_CLOUD_SECRET_MANAGER:
        return GoogleCloudSecretManagerClient(backend)
    if backend.backend_type == VaultBackendTypeChoices.AWS_SECRETS_MANAGER:
        return AWSSecretsManagerClient(backend)
    raise BackendConfigurationError(f"Unsupported backend type '{backend.backend_type}'.")
