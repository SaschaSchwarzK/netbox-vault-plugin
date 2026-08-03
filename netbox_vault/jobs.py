from core.choices import JobIntervalChoices
from core.exceptions import JobFailed
from netbox.jobs import JobRunner, system_job

from .secrets import refresh_all_secrets


@system_job(interval=JobIntervalChoices.INTERVAL_HOURLY)
class RefreshDueVaultSecretsJob(JobRunner):
    class Meta:
        name = "Refresh due vault secrets"
        description = (
            "Runs every hour, scans all enabled cached secrets, and refreshes only those whose "
            "configured refresh interval has elapsed."
        )

    def run(self, *args, **kwargs):
        refreshed, failures = refresh_all_secrets(due_only=True, raise_on_failure=False)

        if hasattr(self, "log_info"):
            self.log_info(f"Refreshed {len(refreshed)} due secret(s).")
            if failures:
                for name, error in failures:
                    self.log_warning(f"Failed to refresh {name}: {error}")

        if failures:
            raise JobFailed(f"{len(failures)} secret refresh operation(s) failed.")

        return {
            "refreshed": len(refreshed),
            "failed": len(failures),
        }
