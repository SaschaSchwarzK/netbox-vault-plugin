from __future__ import annotations

from collections.abc import Iterable

from django.db import connection
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .backends import SecretRefreshError, get_vault_client
from .cache import (
    delete_cached_secret,
    get_cached_secret_value as get_cached_secret_value_from_cache,
    has_cached_secret,
    mark_startup_sync_completed,
    startup_sync_completed_recently,
    acquire_startup_sync_lock,
    release_startup_sync_lock,
    write_cached_secret,
)
from .models import RefreshStatusChoices, VaultSecret


class BulkRefreshError(RuntimeError):
    def __init__(self, failures: list[tuple[str, str]]):
        self.failures = failures
        super().__init__(f"{len(failures)} secret refresh operation(s) failed.")


def _vault_tables_ready() -> bool:
    try:
        return VaultSecret._meta.db_table in connection.introspection.table_names()
    except (OperationalError, ProgrammingError):
        return False


def get_secret_record(identifier) -> VaultSecret:
    if isinstance(identifier, VaultSecret):
        return identifier
    if isinstance(identifier, int):
        return VaultSecret.objects.select_related("vault_backend").get(pk=identifier)
    if isinstance(identifier, str) and identifier.isdigit():
        return VaultSecret.objects.select_related("vault_backend").get(pk=int(identifier))
    return VaultSecret.objects.select_related("vault_backend").get(name=identifier)


def get_cached_secret_value(identifier) -> str:
    secret = get_secret_record(identifier)
    return get_cached_secret_value_from_cache(secret)


def refresh_secret(secret: VaultSecret) -> VaultSecret:
    secret = get_secret_record(secret)
    secret.last_refresh_attempt = timezone.now()
    try:
        plaintext = get_vault_client(secret.vault_backend).fetch_secret(secret)
        secret.last_refreshed = timezone.now()
        secret.last_refresh_status = RefreshStatusChoices.SYNCED
        secret.last_refresh_error = ""
        write_cached_secret(secret, plaintext)
        secret.cache_present = True
    except Exception as exc:
        if secret.last_refreshed and has_cached_secret(secret):
            secret.last_refresh_status = RefreshStatusChoices.STALE
        else:
            secret.last_refresh_status = RefreshStatusChoices.FAILED
            secret.cache_present = False
        secret.last_refresh_error = str(exc)
        secret.save(
            update_fields=(
                "cache_present",
                "last_refresh_attempt",
                "last_refresh_status",
                "last_refresh_error",
                "last_updated",
            )
        )
        if isinstance(exc, SecretRefreshError):
            raise
        raise SecretRefreshError(str(exc)) from exc

    secret.save(
        update_fields=(
            "cache_present",
            "last_refreshed",
            "last_refresh_attempt",
            "last_refresh_status",
            "last_refresh_error",
            "last_updated",
        )
    )
    return secret


def _refresh_matching_secrets(secrets: Iterable[VaultSecret], raise_on_failure: bool = False) -> tuple[list[VaultSecret], list[tuple[str, str]]]:
    refreshed = []
    failures = []
    for secret in secrets:
        try:
            refreshed.append(refresh_secret(secret))
        except Exception as exc:
            failures.append((secret.name, str(exc)))

    if failures and raise_on_failure:
        raise BulkRefreshError(failures)
    return refreshed, failures


def refresh_all_secrets(due_only: bool = False, raise_on_failure: bool = False) -> tuple[list[VaultSecret], list[tuple[str, str]]]:
    queryset = VaultSecret.objects.select_related("vault_backend").filter(
        enabled=True,
        vault_backend__enabled=True,
    )
    if due_only:
        queryset = [secret for secret in queryset if secret.is_refresh_due]
    return _refresh_matching_secrets(queryset, raise_on_failure=raise_on_failure)


def get_secret_value(identifier, refresh_if_due: bool = False, allow_stale: bool = True) -> str:
    secret = get_secret_record(identifier)
    if refresh_if_due and secret.is_refresh_due:
        try:
            secret = refresh_secret(secret)
        except SecretRefreshError:
            if not allow_stale or not has_cached_secret(secret):
                raise
    return get_cached_secret_value(secret)


def iter_due_secrets() -> Iterable[VaultSecret]:
    for secret in VaultSecret.objects.select_related("vault_backend").filter(
        enabled=True,
        vault_backend__enabled=True,
    ):
        if secret.is_refresh_due:
            yield secret


def iter_due_or_missing_cache_secrets() -> Iterable[VaultSecret]:
    for secret in VaultSecret.objects.select_related("vault_backend").filter(
        enabled=True,
        vault_backend__enabled=True,
    ):
        if secret.is_refresh_due or (secret.cache_present and not has_cached_secret(secret)):
            yield secret


def refresh_due_or_missing_cache_secrets(raise_on_failure: bool = False) -> tuple[list[VaultSecret], list[tuple[str, str]]]:
    return _refresh_matching_secrets(iter_due_or_missing_cache_secrets(), raise_on_failure=raise_on_failure)


def clear_secret_cache(secret):
    secret = get_secret_record(secret)
    delete_cached_secret(secret)
    if secret.cache_present:
        secret.cache_present = False
        secret.save(update_fields=("cache_present", "last_updated"))


def run_startup_secret_sync() -> tuple[list[VaultSecret], list[tuple[str, str]]] | None:
    if not _vault_tables_ready():
        return None

    if startup_sync_completed_recently():
        return None

    lock_token = acquire_startup_sync_lock()
    if not lock_token:
        return None

    try:
        refreshed, failures = refresh_due_or_missing_cache_secrets(raise_on_failure=False)
        mark_startup_sync_completed()
        return refreshed, failures
    finally:
        release_startup_sync_lock(lock_token)
