from django.test import TestCase

from netbox_vault.forms import VaultBackendForm


class VaultBackendFormTests(TestCase):
    def test_hashicorp_backend_requires_secret_engine(self):
        form = VaultBackendForm(
            data={
                'name': 'backend-a',
                'backend_type': 'hashicorp',
                'api_url': 'https://vault.example.com',
                'secret_engine': '',
                'default_namespace': '',
                'azure_api_version': '7.5',
                'enabled': True,
                'description': '',
                'extra_config': '{}',
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('secret_engine', form.errors)

    def test_non_hashicorp_backend_allows_empty_secret_engine(self):
        form = VaultBackendForm(
            data={
                'name': 'backend-b',
                'backend_type': 'azure_key_vault',
                'api_url': 'https://example.vault.azure.net',
                'secret_engine': '',
                'default_namespace': '',
                'azure_api_version': '7.5',
                'enabled': True,
                'description': '',
                'extra_config': '{}',
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
