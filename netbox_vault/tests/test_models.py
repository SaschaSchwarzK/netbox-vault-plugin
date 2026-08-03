from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from netbox_vault.models import RefreshStatusChoices, VaultBackend, VaultSecret


class VaultSecretModelTests(TestCase):
    def setUp(self):
        self.backend = VaultBackend.objects.create(
            name='backend-a',
            backend_type='hashicorp',
            api_url='https://vault.example.com',
            secret_engine='secret',
        )

    def test_has_cached_value_reflects_cache_present_flag(self):
        secret = VaultSecret.objects.create(
            name='secret-a',
            vault_backend=self.backend,
            secret_path='path/a',
        )
        self.assertFalse(secret.has_cached_value)

        secret.cache_present = True
        self.assertTrue(secret.has_cached_value)

    def test_next_refresh_at_and_is_refresh_due_without_last_refresh(self):
        secret = VaultSecret.objects.create(
            name='secret-b',
            vault_backend=self.backend,
            secret_path='path/b',
            refresh_interval_hours=4,
        )

        self.assertIsNone(secret.next_refresh_at)
        self.assertTrue(secret.is_refresh_due)

    def test_next_refresh_at_and_is_refresh_due_after_refresh(self):
        last_refreshed = timezone.now() - timedelta(hours=2)
        secret = VaultSecret.objects.create(
            name='secret-c',
            vault_backend=self.backend,
            secret_path='path/c',
            refresh_interval_hours=3,
            last_refreshed=last_refreshed,
            last_refresh_status=RefreshStatusChoices.SYNCED,
        )

        self.assertEqual(secret.next_refresh_at, last_refreshed + timedelta(hours=3))
        self.assertFalse(secret.is_refresh_due)

        secret.last_refreshed = timezone.now() - timedelta(hours=4)
        self.assertTrue(secret.is_refresh_due)
