from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from netbox_vault.backends import SecretRefreshError
from netbox_vault.crypto import SecretDecryptionError
from netbox_vault.models import RefreshStatusChoices, VaultBackend, VaultSecret
from netbox_vault.secrets import (
    BulkRefreshError,
    clear_secret_cache,
    get_cached_secret_value,
    get_secret_record,
    get_secret_value,
    iter_due_or_missing_cache_secrets,
    iter_due_secrets,
    refresh_all_secrets,
    refresh_due_or_missing_cache_secrets,
    refresh_secret,
    run_startup_secret_sync,
    set_secret_value,
)


class SecretServiceTests(TestCase):
    def setUp(self):
        self.backend = VaultBackend.objects.create(
            name='backend-a',
            backend_type='hashicorp',
            api_url='https://vault.example.com',
            secret_engine='secret',
        )

    def create_secret(self, name='secret-a', **kwargs):
        defaults = {
            'vault_backend': self.backend,
            'secret_path': f'path/{name}',
            'secret_key': 'value',
            'refresh_interval_hours': 1,
            'enabled': True,
        }
        defaults.update(kwargs)
        return VaultSecret.objects.create(name=name, **defaults)

    def test_get_secret_record_supports_instance_id_and_name(self):
        secret = self.create_secret('record-secret')

        self.assertEqual(get_secret_record(secret), secret)
        self.assertEqual(get_secret_record(secret.pk).pk, secret.pk)
        self.assertEqual(get_secret_record(str(secret.pk)).pk, secret.pk)
        self.assertEqual(get_secret_record(secret.name).pk, secret.pk)

    @patch('netbox_vault.secrets.get_cached_secret_value_from_cache')
    def test_get_cached_secret_value_requires_cached_data(self, cached_value_mock):
        secret = self.create_secret('empty-secret')
        cached_value_mock.side_effect = SecretDecryptionError('missing cache')
        with self.assertRaises(SecretDecryptionError):
            get_cached_secret_value(secret)

    @patch('netbox_vault.secrets.write_cached_secret')
    @patch('netbox_vault.secrets.get_cached_secret_value_from_cache')
    @patch('netbox_vault.secrets.get_vault_client')
    def test_refresh_secret_success_updates_cache_and_status(self, get_vault_client_mock, cached_value_mock, write_cached_secret_mock):
        secret = self.create_secret('refresh-success')
        get_vault_client_mock.return_value.fetch_secret.return_value = 'plaintext-value'
        cached_value_mock.return_value = 'plaintext-value'

        refreshed = refresh_secret(secret)
        refreshed.refresh_from_db()

        self.assertEqual(refreshed.last_refresh_status, RefreshStatusChoices.SYNCED)
        self.assertEqual(refreshed.last_refresh_error, '')
        self.assertTrue(refreshed.cache_present)
        write_cached_secret_mock.assert_called_once()
        self.assertEqual(get_secret_value(refreshed.name), 'plaintext-value')

    @patch('netbox_vault.secrets.write_cached_secret')
    @patch('netbox_vault.secrets.get_vault_client')
    def test_set_secret_value_updates_upstream_and_cache(self, get_vault_client_mock, write_cached_secret_mock):
        secret = self.create_secret('set-secret')

        updated = set_secret_value(secret, 'new-value')
        updated.refresh_from_db()

        get_vault_client_mock.return_value.store_secret.assert_called_once_with(secret, 'new-value')
        write_cached_secret_mock.assert_called_once_with(updated, 'new-value')
        self.assertEqual(updated.last_refresh_status, RefreshStatusChoices.SYNCED)
        self.assertTrue(updated.cache_present)

    @patch('netbox_vault.secrets.get_vault_client')
    def test_set_secret_value_rejects_read_only_backend(self, get_vault_client_mock):
        self.backend.read_only = True
        self.backend.save(update_fields=('read_only', 'last_updated'))
        secret = self.create_secret('set-read-only')

        with self.assertRaises(SecretRefreshError) as ctx:
            set_secret_value(secret, 'new-value')

        self.assertIn('read-only', str(ctx.exception))
        get_vault_client_mock.assert_not_called()


    @patch('netbox_vault.secrets.has_cached_secret', return_value=False)
    @patch('netbox_vault.secrets.get_vault_client')
    def test_refresh_secret_failure_without_previous_cache_marks_failed(self, get_vault_client_mock, has_cached_secret_mock):
        secret = self.create_secret('refresh-fail-empty')
        get_vault_client_mock.return_value.fetch_secret.side_effect = RuntimeError('boom')

        with self.assertRaises(SecretRefreshError):
            refresh_secret(secret)

        secret.refresh_from_db()
        self.assertEqual(secret.last_refresh_status, RefreshStatusChoices.FAILED)
        self.assertEqual(secret.last_refresh_error, 'boom')
        self.assertIsNone(secret.last_refreshed)
        self.assertFalse(secret.cache_present)
        has_cached_secret_mock.assert_not_called()

    @patch('netbox_vault.secrets.has_cached_secret', return_value=True)
    @patch('netbox_vault.secrets.get_vault_client')
    def test_refresh_secret_failure_with_previous_cache_marks_stale(self, get_vault_client_mock, has_cached_secret_mock):
        secret = self.create_secret(
            'refresh-fail-stale',
            cache_present=True,
            last_refreshed=timezone.now() - timedelta(hours=2),
        )
        get_vault_client_mock.return_value.fetch_secret.side_effect = RuntimeError('still failing')

        with self.assertRaises(SecretRefreshError):
            refresh_secret(secret)

        secret.refresh_from_db()
        self.assertEqual(secret.last_refresh_status, RefreshStatusChoices.STALE)
        self.assertEqual(secret.last_refresh_error, 'still failing')
        self.assertTrue(secret.cache_present)
        has_cached_secret_mock.assert_called_once()

    @patch('netbox_vault.secrets.has_cached_secret', return_value=True)
    @patch('netbox_vault.secrets.get_vault_client')
    def test_set_secret_value_failure_with_previous_cache_marks_stale(self, get_vault_client_mock, has_cached_secret_mock):
        secret = self.create_secret('set-fail-stale', cache_present=True, last_refreshed=timezone.now() - timedelta(hours=2))
        get_vault_client_mock.return_value.store_secret.side_effect = RuntimeError('write failed')

        with self.assertRaises(SecretRefreshError):
            set_secret_value(secret, 'new-value')

        secret.refresh_from_db()
        self.assertEqual(secret.last_refresh_status, RefreshStatusChoices.STALE)
        self.assertEqual(secret.last_refresh_error, 'write failed')
        self.assertTrue(secret.cache_present)
        has_cached_secret_mock.assert_called_once()

    @patch('netbox_vault.secrets.refresh_secret')
    def test_refresh_all_secrets_due_only_filters_and_collects_failures(self, refresh_secret_mock):
        due_secret = self.create_secret('due-secret', last_refreshed=timezone.now() - timedelta(hours=5))
        fresh_secret = self.create_secret('fresh-secret', last_refreshed=timezone.now())
        disabled_secret = self.create_secret('disabled-secret', enabled=False)

        def fake_refresh(secret):
            if secret.name == due_secret.name:
                return secret
            raise AssertionError('unexpected secret refresh')

        refresh_secret_mock.side_effect = fake_refresh
        refreshed, failures = refresh_all_secrets(due_only=True, raise_on_failure=False)

        self.assertEqual([secret.name for secret in refreshed], [due_secret.name])
        self.assertEqual(failures, [])
        self.assertNotIn(disabled_secret.name, [secret.name for secret in refreshed])
        self.assertNotIn(fresh_secret.name, [secret.name for secret in refreshed])

    @patch('netbox_vault.secrets.refresh_secret')
    def test_refresh_all_secrets_can_raise_bulk_refresh_error(self, refresh_secret_mock):
        secret = self.create_secret('bulk-failure')
        refresh_secret_mock.side_effect = SecretRefreshError('bad refresh')

        with self.assertRaises(BulkRefreshError) as ctx:
            refresh_all_secrets(due_only=False, raise_on_failure=True)

        self.assertEqual(ctx.exception.failures, [(secret.name, 'bad refresh')])

    @patch('netbox_vault.secrets.get_cached_secret_value_from_cache', return_value='cached-stale-value')
    @patch('netbox_vault.secrets.has_cached_secret', return_value=True)
    @patch('netbox_vault.secrets.refresh_secret')
    def test_get_secret_value_can_return_stale_cache_when_refresh_if_due_fails(self, refresh_secret_mock, has_cached_secret_mock, cached_value_mock):
        secret = self.create_secret(
            'stale-allowed',
            cache_present=True,
            last_refreshed=timezone.now() - timedelta(hours=2),
            last_refresh_status=RefreshStatusChoices.STALE,
        )
        refresh_secret_mock.side_effect = SecretRefreshError('upstream unavailable')

        self.assertEqual(get_secret_value(secret.name, refresh_if_due=True, allow_stale=True), 'cached-stale-value')
        has_cached_secret_mock.assert_called_once()
        cached_value_mock.assert_called_once()

    @patch('netbox_vault.secrets.has_cached_secret', return_value=False)
    @patch('netbox_vault.secrets.refresh_secret')
    def test_get_secret_value_raises_when_stale_not_allowed(self, refresh_secret_mock, has_cached_secret_mock):
        secret = self.create_secret(
            'stale-disallowed',
            last_refreshed=timezone.now() - timedelta(hours=2),
        )
        refresh_secret_mock.side_effect = SecretRefreshError('upstream unavailable')

        with self.assertRaises(SecretRefreshError):
            get_secret_value(secret.name, refresh_if_due=True, allow_stale=False)

        has_cached_secret_mock.assert_not_called()

    def test_iter_due_secrets_returns_enabled_due_records_only(self):
        due_secret = self.create_secret('due-iter', last_refreshed=timezone.now() - timedelta(hours=2))
        self.create_secret('fresh-iter', last_refreshed=timezone.now())
        self.create_secret('disabled-iter', enabled=False, last_refreshed=timezone.now() - timedelta(hours=2))

        due_names = [secret.name for secret in iter_due_secrets()]
        self.assertEqual(due_names, [due_secret.name])

    @patch('netbox_vault.secrets.has_cached_secret', side_effect=[False, True])
    def test_iter_due_or_missing_cache_secrets_includes_due_and_missing_cached_records(self, has_cached_secret_mock):
        due_secret = self.create_secret('due-missing', last_refreshed=timezone.now() - timedelta(hours=2))
        cached_missing = self.create_secret('cached-missing', cache_present=True, last_refreshed=timezone.now())
        self.create_secret('cached-present', cache_present=True, last_refreshed=timezone.now())

        names = [secret.name for secret in iter_due_or_missing_cache_secrets()]
        self.assertEqual(names, [cached_missing.name, due_secret.name])
        self.assertEqual(has_cached_secret_mock.call_count, 2)

    @patch('netbox_vault.secrets.refresh_secret')
    @patch('netbox_vault.secrets.has_cached_secret', side_effect=[False])
    def test_refresh_due_or_missing_cache_secrets_refreshes_missing_cache_records(self, has_cached_secret_mock, refresh_secret_mock):
        secret = self.create_secret('missing-cache-refresh', cache_present=True, last_refreshed=timezone.now())
        refresh_secret_mock.return_value = secret

        refreshed, failures = refresh_due_or_missing_cache_secrets(raise_on_failure=False)

        self.assertEqual([item.name for item in refreshed], [secret.name])
        self.assertEqual(failures, [])
        has_cached_secret_mock.assert_called_once()

    @patch('netbox_vault.secrets.delete_cached_secret')
    def test_clear_secret_cache_deletes_redis_value_and_updates_metadata(self, delete_cached_secret_mock):
        secret = self.create_secret('clear-cache', cache_present=True)

        clear_secret_cache(secret)
        secret.refresh_from_db()

        delete_cached_secret_mock.assert_called_once()
        self.assertFalse(secret.cache_present)

    @patch('netbox_vault.secrets.release_startup_sync_lock')
    @patch('netbox_vault.secrets.mark_startup_sync_completed')
    @patch('netbox_vault.secrets.refresh_due_or_missing_cache_secrets', return_value=(['one'], []))
    @patch('netbox_vault.secrets.acquire_startup_sync_lock', return_value='lock-token')
    @patch('netbox_vault.secrets.startup_sync_completed_recently', return_value=False)
    def test_run_startup_secret_sync_refreshes_due_or_missing_secrets_once(self, completed_mock, acquire_mock, refresh_mock, mark_mock, release_mock):
        result = run_startup_secret_sync()

        self.assertEqual(result, (['one'], []))
        completed_mock.assert_called_once()
        acquire_mock.assert_called_once()
        refresh_mock.assert_called_once_with(raise_on_failure=False)
        mark_mock.assert_called_once()
        release_mock.assert_called_once_with('lock-token')

    @patch('netbox_vault.secrets.acquire_startup_sync_lock')
    @patch('netbox_vault.secrets.startup_sync_completed_recently', return_value=True)
    def test_run_startup_secret_sync_skips_when_recent_marker_exists(self, completed_mock, acquire_mock):
        self.assertIsNone(run_startup_secret_sync())
        acquire_mock.assert_not_called()
