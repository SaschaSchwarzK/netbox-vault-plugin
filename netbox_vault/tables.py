import django_tables2 as tables
from django.utils.translation import gettext_lazy as _

from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from .models import VaultBackend, VaultSecret


class VaultBackendTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    backend_type = tables.Column(verbose_name=_("Type"))
    api_url = tables.Column(verbose_name=_("API URL"))
    read_only = BooleanColumn(verbose_name=_("Read only"))
    enabled = BooleanColumn(verbose_name=_("Enabled"))

    class Meta(NetBoxTable.Meta):
        model = VaultBackend
        fields = ("pk", "id", "name", "backend_type", "api_url", "read_only", "enabled", "last_updated")
        default_columns = ("name", "backend_type", "api_url", "read_only", "enabled", "last_updated")


class VaultSecretTable(NetBoxTable):
    name = tables.Column(linkify=True, verbose_name=_("Name"))
    vault_backend = tables.Column(linkify=True, verbose_name=_("Vault backend"))
    secret_path = tables.Column(verbose_name=_("Secret path"))
    refresh_interval_hours = tables.Column(verbose_name=_("Refresh interval (h)"))
    last_refresh_status = tables.Column(verbose_name=_("Refresh status"))
    enabled = BooleanColumn(verbose_name=_("Enabled"))

    class Meta(NetBoxTable.Meta):
        model = VaultSecret
        fields = (
            "pk",
            "id",
            "name",
            "vault_backend",
            "secret_path",
            "refresh_interval_hours",
            "last_refreshed",
            "last_refresh_status",
            "enabled",
            "last_updated",
        )
        default_columns = (
            "name",
            "vault_backend",
            "secret_path",
            "refresh_interval_hours",
            "last_refreshed",
            "last_refresh_status",
            "enabled",
        )
