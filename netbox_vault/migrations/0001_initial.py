from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from utilities.json import CustomFieldJSONEncoder


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="VaultBackend",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)),
                ("name", models.CharField(max_length=100, unique=True)),
                (
                    "backend_type",
                    models.CharField(
                        choices=[
                            ("hashicorp", "HashiCorp Vault"),
                            ("azure_key_vault", "Azure Key Vault"),
                            ("google_cloud_secret_manager", "Google Cloud Secret Manager"),
                            ("aws_secrets_manager", "AWS Secrets Manager"),
                        ],
                        max_length=32,
                    ),
                ),
                ("api_url", models.URLField(help_text="Provider endpoint. Examples: HashiCorp Vault base URL, Azure Key Vault URL, Google Secret Manager API endpoint, or AWS Secrets Manager endpoint override.")),
                ("secret_engine", models.CharField(blank=True, default="", help_text="HashiCorp KV v2 mount path, for example 'secret'. Ignored by other providers.", max_length=100)),
                ("default_namespace", models.CharField(blank=True, default="", help_text="Optional HashiCorp namespace. Ignored by Azure, Google Cloud, and AWS.", max_length=100)),
                ("azure_api_version", models.CharField(blank=True, default="7.5", help_text="Azure Key Vault API version. Ignored by other providers.", max_length=20)),
                ("enabled", models.BooleanField(default=True)),
                ("description", models.TextField(blank=True)),
                ("extra_config", models.JSONField(blank=True, default=dict)),
            ],
            options={"verbose_name": "Vault backend", "verbose_name_plural": "Vault backends", "ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="VaultSecret",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("last_updated", models.DateTimeField(auto_now=True)),
                ("custom_field_data", models.JSONField(blank=True, default=dict, encoder=CustomFieldJSONEncoder)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("secret_path", models.CharField(help_text="Provider secret identifier. Examples: Vault path, Azure secret name, Google secret resource path, or AWS secret name/ARN.", max_length=255)),
                ("secret_key", models.CharField(default="value", help_text="Field inside the upstream secret payload for HashiCorp Vault. Ignored by Azure, Google Cloud, and AWS.", max_length=100)),
                ("refresh_interval_hours", models.PositiveSmallIntegerField(default=1, help_text="How often the cached secret should be refreshed from the external vault.", validators=[MinValueValidator(1), MaxValueValidator(24)])),
                ("encrypted_value", models.TextField(blank=True, editable=False)),
                ("last_refreshed", models.DateTimeField(blank=True, null=True)),
                ("last_refresh_attempt", models.DateTimeField(blank=True, null=True)),
                ("last_refresh_status", models.CharField(choices=[("unknown", "Unknown"), ("synced", "Synced"), ("failed", "Failed"), ("stale", "Stale")], default="unknown", max_length=16)),
                ("last_refresh_error", models.TextField(blank=True)),
                ("enabled", models.BooleanField(default=True)),
                ("description", models.TextField(blank=True)),
                ("vault_backend", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="secrets", to="netbox_vault.vaultbackend")),
            ],
            options={"verbose_name": "Vault secret", "verbose_name_plural": "Vault secrets", "ordering": ("name",)},
        ),
    ]
