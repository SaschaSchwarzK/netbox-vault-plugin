from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from ..models import VaultBackend, VaultSecret


class VaultBackendSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_vault-api:vaultbackend-detail",
    )

    class Meta:
        model = VaultBackend
        fields = (
            "id",
            "url",
            "display",
            "name",
            "backend_type",
            "api_url",
            "secret_engine",
            "default_namespace",
            "azure_api_version",
            "read_only",
            "enabled",
            "description",
            "extra_config",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class VaultBackendNestedSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_vault-api:vaultbackend-detail",
    )

    class Meta:
        model = VaultBackend
        fields = ("id", "url", "display", "name", "backend_type", "read_only")
        brief_fields = fields


class VaultSecretSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_vault-api:vaultsecret-detail",
    )
    vault_backend = VaultBackendNestedSerializer(nested=True, read_only=True)
    vault_backend_id = serializers.PrimaryKeyRelatedField(
        source="vault_backend",
        queryset=VaultBackend.objects.all(),
        write_only=True,
    )
    has_cached_value = serializers.BooleanField(read_only=True)
    next_refresh_at = serializers.DateTimeField(read_only=True)
    is_refresh_due = serializers.BooleanField(read_only=True)

    class Meta:
        model = VaultSecret
        fields = (
            "id",
            "url",
            "display",
            "name",
            "vault_backend",
            "vault_backend_id",
            "secret_path",
            "secret_key",
            "refresh_interval_hours",
            "last_refreshed",
            "last_refresh_attempt",
            "last_refresh_status",
            "last_refresh_error",
            "has_cached_value",
            "next_refresh_at",
            "is_refresh_due",
            "enabled",
            "description",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name")


class VaultSecretSetValueSerializer(serializers.Serializer):
    value = serializers.CharField(write_only=True, allow_blank=False, trim_whitespace=False)
