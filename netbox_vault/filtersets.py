import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from utilities.filtersets import register_filterset

from .models import VaultBackend, VaultSecret


@register_filterset
class VaultBackendFilterSet(NetBoxModelFilterSet):
    enabled = django_filters.BooleanFilter()

    class Meta:
        model = VaultBackend
        fields = ("id", "name", "backend_type", "enabled")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(api_url__icontains=value))


@register_filterset
class VaultSecretFilterSet(NetBoxModelFilterSet):
    vault_backend_id = django_filters.ModelMultipleChoiceFilter(queryset=VaultBackend.objects.all())
    enabled = django_filters.BooleanFilter()

    class Meta:
        model = VaultSecret
        fields = ("id", "name", "vault_backend_id", "last_refresh_status", "enabled")

    def search(self, queryset, name, value):
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(secret_path__icontains=value) | Q(vault_backend__name__icontains=value))
