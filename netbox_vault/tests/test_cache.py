from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from netbox_vault.cache import (
    CachedSecretPayload,
    delete_cached_secret,
    get_cache_key,
    get_cached_secret_value,
    invalidate_local_secret_cache,
    read_cached_secret_payload,
    write_cached_secret,
)
from netbox_vault.crypto import SecretDecryptionError
from netbox_vault.models import VaultSecret


class SecretCacheTests(SimpleTestCase):
    def tearDown(self):
        invalidate_local_secret_cache()
        super().tearDown()

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

    @patch('netbox_vault.cache.decrypt_value', return_value='plaintext-value')
    @patch('netbox_vault.cache.get_redis_client')
    def test_get_cached_secret_value_uses_short_lived_process_cache(self, get_redis_client_mock, decrypt_value_mock):
        client = Mock()
        client.get.return_value = '{"ciphertext": "ciphertext"}'
        get_redis_client_mock.return_value = client

        secret = VaultSecret(pk=11, name='secret-d')

        self.assertEqual(get_cached_secret_value(secret), 'plaintext-value')
        self.assertEqual(get_cached_secret_value(secret), 'plaintext-value')

        client.get.assert_called_once()
        decrypt_value_mock.assert_called_once_with('ciphertext')

    @patch('netbox_vault.cache.encrypt_value', return_value='ciphertext-2')
    @patch('netbox_vault.cache.decrypt_value', side_effect=['plaintext-value', 'updated-value'])
    @patch('netbox_vault.cache.get_redis_client')
    def test_write_cached_secret_invalidates_process_cache(self, get_redis_client_mock, decrypt_value_mock, encrypt_value_mock):
        client = Mock()
        client.get.side_effect = [
            '{"ciphertext": "ciphertext-1"}',
            '{"ciphertext": "ciphertext-2"}',
        ]
        get_redis_client_mock.return_value = client
        secret = VaultSecret(pk=12, name='secret-e', last_refresh_status='synced')

        self.assertEqual(get_cached_secret_value(secret), 'plaintext-value')
        write_cached_secret(secret, 'updated-value')
        self.assertEqual(get_cached_secret_value(secret), 'updated-value')

        self.assertEqual(client.get.call_count, 2)
        self.assertEqual(decrypt_value_mock.call_count, 2)
        encrypt_value_mock.assert_called_once_with('updated-value')

    @patch('netbox_vault.cache.decrypt_value', return_value='plaintext-value')
    @patch('netbox_vault.cache.get_redis_client')
    def test_delete_cached_secret_invalidates_process_cache(self, get_redis_client_mock, decrypt_value_mock):
        client = Mock()
        client.get.side_effect = [
            '{"ciphertext": "ciphertext"}',
            None,
        ]
        get_redis_client_mock.return_value = client
        secret = VaultSecret(pk=13, name='secret-f')

        self.assertEqual(get_cached_secret_value(secret), 'plaintext-value')
        delete_cached_secret(secret)
        with self.assertRaises(SecretDecryptionError):
            get_cached_secret_value(secret)

        self.assertEqual(client.get.call_count, 2)
        client.delete.assert_called_once_with(get_cache_key(secret))
