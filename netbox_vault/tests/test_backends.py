from django.test import SimpleTestCase
from unittest.mock import patch

from netbox_vault.backends import (
    AWSSecretsManagerClient,
    AzureKeyVaultClient,
    GoogleCloudSecretManagerClient,
    HashiCorpVaultClient,
    _get_backend_credentials,
    _get_request_verify,
    get_vault_client,
)
from netbox_vault.models import VaultBackend, VaultBackendTypeChoices, VaultSecret


class BackendHelpersTests(SimpleTestCase):
    def test_backend_credentials_resolve_by_backend_name_first(self):
        backend = VaultBackend(name='backend-name', backend_type='hashicorp', api_url='https://vault.example.com')
        with patch('netbox_vault.backends._plugin_setting', return_value={'backend-name': {'token': 'abc'}}):
            self.assertEqual(_get_backend_credentials(backend), {'token': 'abc'})

    def test_backend_credentials_resolve_by_credentials_key_alias(self):
        backend = VaultBackend(
            name='display-name',
            backend_type='hashicorp',
            api_url='https://vault.example.com',
            extra_config={'credentials_key': 'shared-key'},
        )
        with patch('netbox_vault.backends._plugin_setting', return_value={'shared-key': {'token': 'xyz'}}):
            self.assertEqual(_get_backend_credentials(backend), {'token': 'xyz'})

    def test_request_verify_defaults_to_true_and_honors_extra_config(self):
        backend = VaultBackend(name='backend-name', backend_type='azure_key_vault', api_url='https://vault.example.com')
        self.assertTrue(_get_request_verify(backend))

        backend.extra_config = {'verify_tls': False}
        self.assertFalse(_get_request_verify(backend))

    def test_google_resource_builder_supports_short_and_full_paths(self):
        backend = VaultBackend(
            name='gcp-backend',
            backend_type=VaultBackendTypeChoices.GOOGLE_CLOUD_SECRET_MANAGER,
            api_url='https://secretmanager.googleapis.com',
            extra_config={'project_id': 'demo-project'},
        )
        client = GoogleCloudSecretManagerClient(backend)

        self.assertEqual(
            client._build_secret_resource(VaultSecret(name='a', vault_backend=backend, secret_path='db-password')),
            'projects/demo-project/secrets/db-password/versions/latest',
        )
        self.assertEqual(
            client._build_secret_resource(VaultSecret(name='b', vault_backend=backend, secret_path='db-password/versions/5')),
            'projects/demo-project/secrets/db-password/versions/5',
        )
        self.assertEqual(
            client._build_secret_resource(
                VaultSecret(name='c', vault_backend=backend, secret_path='projects/x/secrets/y/versions/latest')
            ),
            'projects/x/secrets/y/versions/latest',
        )

    def test_aws_region_name_can_be_inferred_from_endpoint(self):
        backend = VaultBackend(
            name='aws-backend',
            backend_type=VaultBackendTypeChoices.AWS_SECRETS_MANAGER,
            api_url='https://secretsmanager.eu-central-1.amazonaws.com',
        )
        client = AWSSecretsManagerClient(backend)
        self.assertEqual(client._get_region_name(), 'eu-central-1')

    def test_get_vault_client_returns_expected_client_class(self):
        backend_types = {
            VaultBackendTypeChoices.HASHICORP: HashiCorpVaultClient,
            VaultBackendTypeChoices.AZURE_KEY_VAULT: AzureKeyVaultClient,
            VaultBackendTypeChoices.GOOGLE_CLOUD_SECRET_MANAGER: GoogleCloudSecretManagerClient,
            VaultBackendTypeChoices.AWS_SECRETS_MANAGER: AWSSecretsManagerClient,
        }

        for backend_type, expected_class in backend_types.items():
            backend = VaultBackend(name=f'{backend_type}-backend', backend_type=backend_type, api_url='https://example.com')
            self.assertIsInstance(get_vault_client(backend), expected_class)
