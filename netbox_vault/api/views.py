from django.db.models import Count
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from .. import filtersets, models
from ..backends import SecretRefreshError
from ..secrets import refresh_all_secrets, refresh_secret, set_secret_value
from .serializers import VaultBackendSerializer, VaultSecretSerializer, VaultSecretSetValueSerializer


class VaultBackendViewSet(NetBoxModelViewSet):
    queryset = models.VaultBackend.objects.annotate(secret_count=Count("secrets"))
    serializer_class = VaultBackendSerializer
    filterset_class = filtersets.VaultBackendFilterSet


class VaultSecretViewSet(NetBoxModelViewSet):
    queryset = models.VaultSecret.objects.select_related("vault_backend")
    serializer_class = VaultSecretSerializer
    filterset_class = filtersets.VaultSecretFilterSet

    @action(detail=True, methods=["post"])
    def refresh(self, request, pk=None):
        secret = self.get_object()
        secret = refresh_secret(secret)
        serializer = self.get_serializer(secret)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="set-value")
    def set_value(self, request, pk=None):
        secret = self.get_object()
        if secret.vault_backend.read_only:
            return Response(
                {"detail": "This vault backend is configured as read-only."},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = VaultSecretSetValueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            secret = set_secret_value(secret, serializer.validated_data["value"])
        except SecretRefreshError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(self.get_serializer(secret).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="refresh-all")
    def refresh_all_action(self, request):
        due_only = bool(request.data.get("due_only", False))
        refreshed, failures = refresh_all_secrets(due_only=due_only, raise_on_failure=False)
        return Response(
            {
                "refreshed": [secret.name for secret in refreshed],
                "failures": [{"name": name, "error": error} for name, error in failures],
                "due_only": due_only,
            },
            status=status.HTTP_200_OK,
        )
