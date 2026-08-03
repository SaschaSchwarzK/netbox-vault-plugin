from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from netbox_vault.cache import CachedSecretPayload, get_cache_key, get_cached_secret_value, read_cached_secret_payload, write_cached_secret
from netbox_vault.models import VaultSecret


class SecretCacheTests(SimpleTestCase):
    @override_settings(PLUGINS_CONFIG={'netbox_vault': {'redis_key_prefix': 'vault-test'}})
    def test_get_cache_key_uses_configured_prefix(self):
        secret = VaultSecret(pk=42, name='secret-a')
        self.assertEqual(get_cache_key(secret), 'vault-test:secret:42')

    @patch('netbox_vault.cache.get_redis_client')
    def test_read_cached_secret_payload_parses_json_payload(self, get_redis_client_mock):
        client = Mock()
        client.get.return_value = '{"version": 1, "ciphertext": "abc", "refreshed_at": "2026-08-03T08:00:00+00:00", "status": "synced"}'
        get_redis_client_mock.return_value = client

        secret = VaultSecret(pk=1, name='secret-a')
        payload = read_cached_secret_payload(secret)

        self.assertEqual(
            payload,
            CachedSecretPayload(
                ciphertext='abc',
                refreshed_at='2026-08-03T08:00:00+00:00',
                status='synced',
                version=1,
            ),
        )

    @patch('netbox_vault.cache.encrypt_value', return_value='ciphertext')
    @patch('netbox_vault.cache.get_redis_client')
    def test_write_cached_secret_serializes_ciphertext_payload(self, get_redis_client_mock, encrypt_value_mock):
        client = Mock()
        get_redis_client_mock.return_value = client
        secret = VaultSecret(pk=5, name='secret-b', last_refresh_status='synced')

        payload = write_cached_secret(secret, 'plaintext-value')

        client.set.assert_called_once()
        self.assertEqual(payload['ciphertext'], 'ciphertext')
        encrypt_value_mock.assert_called_once_with('plaintext-value')

    @patch('netbox_vault.cache.decrypt_value', return_value='plaintext-value')
    @patch('netbox_vault.cache.get_redis_client')
    def test_get_cached_secret_value_decrypts_cached_ciphertext(self, get_redis_client_mock, decrypt_value_mock):
        client = Mock()
        client.get.return_value = '{"ciphertext": "ciphertext"}'
        get_redis_client_mock.return_value = client

        secret = VaultSecret(pk=9, name='secret-c')
        self.assertEqual(get_cached_secret_value(secret), 'plaintext-value')
        decrypt_value_mock.assert_called_once_with('ciphertext')
