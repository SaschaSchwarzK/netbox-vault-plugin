from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from netbox_vault.api.views import VaultSecretViewSet
from netbox_vault.models import RefreshStatusChoices, VaultBackend, VaultSecret


class VaultSecretApiActionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = get_user_model().objects.create_superuser(
            username='api-admin',
            email='api-admin@example.com',
            password='password123',
        )
        self.backend = VaultBackend.objects.create(
            name='backend-a',
            backend_type='hashicorp',
            api_url='https://vault.example.com',
            secret_engine='secret',
        )
        self.secret = VaultSecret.objects.create(
            name='secret-a',
            vault_backend=self.backend,
            secret_path='path/a',
            last_refresh_status=RefreshStatusChoices.UNKNOWN,
        )

    @patch('netbox_vault.api.views.refresh_secret')
    def test_refresh_action_returns_serialized_secret(self, refresh_secret_mock):
        self.secret.last_refresh_status = RefreshStatusChoices.SYNCED
        refresh_secret_mock.return_value = self.secret

        request = self.factory.post(f'/api/plugins/vault/vault-secrets/{self.secret.pk}/refresh/')
        force_authenticate(request, user=self.user)
        response = VaultSecretViewSet.as_view({'post': 'refresh'})(request, pk=self.secret.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], self.secret.name)
        self.assertEqual(response.data['last_refresh_status'], RefreshStatusChoices.SYNCED)
        refresh_secret_mock.assert_called_once()

    @patch('netbox_vault.api.views.set_secret_value')
    def test_set_value_action_updates_secret_without_returning_plaintext(self, set_secret_value_mock):
        self.secret.last_refresh_status = RefreshStatusChoices.SYNCED
        set_secret_value_mock.return_value = self.secret

        request = self.factory.post(
            f'/api/plugins/vault/vault-secrets/{self.secret.pk}/set-value/',
            {'value': 'new-secret-value'},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = VaultSecretViewSet.as_view({'post': 'set_value'})(request, pk=self.secret.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], self.secret.name)
        self.assertNotIn('value', response.data)
        set_secret_value_mock.assert_called_once_with(self.secret, 'new-secret-value')

    def test_set_value_action_rejects_read_only_backend(self):
        self.backend.read_only = True
        self.backend.save(update_fields=('read_only', 'last_updated'))

        request = self.factory.post(
            f'/api/plugins/vault/vault-secrets/{self.secret.pk}/set-value/',
            {'value': 'new-secret-value'},
            format='json',
        )
        force_authenticate(request, user=self.user)
        response = VaultSecretViewSet.as_view({'post': 'set_value'})(request, pk=self.secret.pk)

        self.assertEqual(response.status_code, 409)
        self.assertIn('read-only', response.data['detail'])

    @patch('netbox_vault.api.views.refresh_all_secrets')
    def test_refresh_all_action_returns_names_and_failures(self, refresh_all_mock):
        other = VaultSecret.objects.create(
            name='secret-b',
            vault_backend=self.backend,
            secret_path='path/b',
        )
        refresh_all_mock.return_value = ([self.secret, other], [('secret-c', 'boom')])

        request = self.factory.post('/api/plugins/vault/vault-secrets/refresh-all/', {'due_only': True}, format='json')
        force_authenticate(request, user=self.user)
        response = VaultSecretViewSet.as_view({'post': 'refresh_all_action'})(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['refreshed'], [self.secret.name, other.name])
        self.assertEqual(response.data['failures'], [{'name': 'secret-c', 'error': 'boom'}])
        self.assertTrue(response.data['due_only'])
        refresh_all_mock.assert_called_once_with(due_only=True, raise_on_failure=False)
