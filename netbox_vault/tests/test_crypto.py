from django.test import SimpleTestCase, override_settings

from netbox_vault.crypto import SecretDecryptionError, decrypt_value, encrypt_value


class CryptoTests(SimpleTestCase):
    @override_settings(SECRET_KEY='unit-test-secret-key')
    def test_encrypt_and_decrypt_round_trip(self):
        encrypted = encrypt_value('super-secret-value')

        self.assertNotEqual(encrypted, 'super-secret-value')
        self.assertEqual(decrypt_value(encrypted), 'super-secret-value')

    @override_settings(SECRET_KEY='unit-test-secret-key')
    def test_decrypt_invalid_value_raises_domain_error(self):
        with self.assertRaises(SecretDecryptionError):
            decrypt_value('not-a-valid-fernet-payload')
