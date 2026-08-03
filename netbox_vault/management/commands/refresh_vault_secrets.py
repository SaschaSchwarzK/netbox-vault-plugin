from django.core.management.base import BaseCommand, CommandError

from netbox_vault.secrets import get_secret_record, iter_due_secrets, refresh_all_secrets, refresh_secret


class Command(BaseCommand):
    help = "Refresh cached vault secrets from upstream providers."

    def add_arguments(self, parser):
        parser.add_argument("--secret", help="Refresh only one secret identified by name or ID.")
        parser.add_argument(
            "--due-only",
            action="store_true",
            help="Refresh only secrets whose refresh interval has elapsed.",
        )

    def handle(self, *args, **options):
        secret_identifier = options.get("secret")
        due_only = options.get("due_only", False)

        if secret_identifier:
            secret = get_secret_record(secret_identifier)
            try:
                refresh_secret(secret)
                self.stdout.write(self.style.SUCCESS(f"Refreshed {secret.name}"))
                return
            except Exception as exc:
                raise CommandError(f"Failed {secret.name}: {exc}") from exc

        if due_only:
            secrets = list(iter_due_secrets())
            failures = []
            for secret in secrets:
                try:
                    refresh_secret(secret)
                    self.stdout.write(self.style.SUCCESS(f"Refreshed {secret.name}"))
                except Exception as exc:
                    failures.append((secret.name, str(exc)))
                    self.stderr.write(self.style.ERROR(f"Failed {secret.name}: {exc}"))
        else:
            refreshed, failures = refresh_all_secrets(due_only=False, raise_on_failure=False)
            for secret in refreshed:
                self.stdout.write(self.style.SUCCESS(f"Refreshed {secret.name}"))
            for name, error in failures:
                self.stderr.write(self.style.ERROR(f"Failed {name}: {error}"))

        if failures:
            raise CommandError(f"{len(failures)} refresh operation(s) failed.")

        if not due_only and not refreshed and not failures:
            self.stdout.write("No enabled secrets were available to refresh.")
        elif due_only and not secrets and not failures:
            self.stdout.write("No due secrets found.")
