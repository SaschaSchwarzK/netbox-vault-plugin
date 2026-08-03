from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from core.exceptions import JobFailed
from netbox_vault.jobs import RefreshDueVaultSecretsJob


class RefreshDueVaultSecretsJobTests(SimpleTestCase):
    @patch('netbox_vault.jobs.refresh_all_secrets', return_value=(['one', 'two'], []))
    def test_job_returns_counts_when_refresh_succeeds(self, refresh_all_mock):
        job = RefreshDueVaultSecretsJob(MagicMock())
        job.log_info = MagicMock()
        job.log_warning = MagicMock()
        result = job.run()

        refresh_all_mock.assert_called_once_with(due_only=True, raise_on_failure=False)
        job.log_info.assert_called_once_with('Refreshed 2 due secret(s).')
        job.log_warning.assert_not_called()
        self.assertEqual(result, {'refreshed': 2, 'failed': 0})

    @patch('netbox_vault.jobs.refresh_all_secrets', return_value=(['one'], [('secret-a', 'boom')]))
    def test_job_raises_when_any_refresh_fails(self, refresh_all_mock):
        job = RefreshDueVaultSecretsJob(MagicMock())
        job.log_info = MagicMock()
        job.log_warning = MagicMock()
        with self.assertRaises(JobFailed):
            job.run()

        refresh_all_mock.assert_called_once_with(due_only=True, raise_on_failure=False)
        job.log_info.assert_called_once_with('Refreshed 1 due secret(s).')
        job.log_warning.assert_called_once_with('Failed to refresh secret-a: boom')
