from datetime import timedelta

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from netbox.models import NetBoxModel


class VaultBackendTypeChoices(models.TextChoices):
    HASHICORP = "hashicorp", _("HashiCorp Vault")
    AZURE_KEY_VAULT = "azure_key_vault", _("Azure Key Vault")
    GOOGLE_CLOUD_SECRET_MANAGER = "google_cloud_secret_manager", _("Google Cloud Secret Manager")
    AWS_SECRETS_MANAGER = "aws_secrets_manager", _("AWS Secrets Manager")


class RefreshStatusChoices(models.TextChoices):
    UNKNOWN = "unknown", _("Unknown")
    SYNCED = "synced", _("Synced")
    FAILED = "failed", _("Failed")
    STALE = "stale", _("Stale")


class VaultBackend(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    backend_type = models.CharField(max_length=32, choices=VaultBackendTypeChoices.choices)
    api_url = models.URLField(
        help_text=_(
            "Provider endpoint. Examples: HashiCorp Vault base URL, Azure Key Vault URL, "
            "Google Secret Manager API endpoint, or AWS Secrets Manager endpoint override."
        )
    )
    secret_engine = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=_("HashiCorp KV v2 mount path, for example 'secret'. Ignored by other providers."),
    )
    default_namespace = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text=_("Optional HashiCorp namespace. Ignored by Azure, Google Cloud, and AWS."),
    )
    azure_api_version = models.CharField(
        max_length=20,
        blank=True,
        default="7.5",
        help_text=_("Azure Key Vault API version. Ignored by other providers."),
    )
    read_only = models.BooleanField(
        default=False,
        help_text=_("Disable all NetBox-driven secret write operations for this backend."),
    )
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    extra_config = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Vault backend")
        verbose_name_plural = _("Vault backends")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_vault:vaultbackend", kwargs={"pk": self.pk})


class VaultSecret(NetBoxModel):
    name = models.CharField(max_length=100, unique=True)
    vault_backend = models.ForeignKey(
        to=VaultBackend,
        on_delete=models.PROTECT,
        related_name="secrets",
    )
    secret_path = models.CharField(
        max_length=255,
        help_text=_(
            "Provider secret identifier. Examples: Vault path, Azure secret name, Google secret resource path, "
            "or AWS secret name/ARN."
        ),
    )
    secret_key = models.CharField(
        max_length=100,
        default="value",
        help_text=_(
            "Field inside the upstream secret payload for HashiCorp Vault. Ignored by Azure, Google Cloud, and AWS."
        ),
    )
    refresh_interval_hours = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(24)],
        help_text=_("How often the cached secret should be refreshed from the external vault."),
    )
    cache_present = models.BooleanField(default=False, editable=False)
    last_refreshed = models.DateTimeField(blank=True, null=True)
    last_refresh_attempt = models.DateTimeField(blank=True, null=True)
    last_refresh_status = models.CharField(
        max_length=16,
        choices=RefreshStatusChoices.choices,
        default=RefreshStatusChoices.UNKNOWN,
    )
    last_refresh_error = models.TextField(blank=True)
    enabled = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ("name",)
        verbose_name = _("Vault secret")
        verbose_name_plural = _("Vault secrets")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plugins:netbox_vault:vaultsecret", kwargs={"pk": self.pk})

    @property
    def has_cached_value(self):
        return bool(self.cache_present)

    @property
    def next_refresh_at(self):
        if self.last_refreshed is None:
            return None
        return self.last_refreshed + timedelta(hours=self.refresh_interval_hours)

    @property
    def is_refresh_due(self):
        if self.last_refreshed is None:
            return True
        return timezone.now() >= self.next_refresh_at
