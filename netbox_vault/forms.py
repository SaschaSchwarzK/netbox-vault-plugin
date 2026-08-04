from django import forms
from django.utils.translation import gettext_lazy as _

from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from utilities.forms.rendering import FieldSet

from .models import VaultBackend, VaultBackendTypeChoices, VaultSecret


BOOLEAN_CHOICES = (("", "---------"), ("true", _("Yes")), ("false", _("No")))


class VaultBackendForm(NetBoxModelForm):
    fieldsets = (
        FieldSet("name", "backend_type", "enabled", "read_only", name=_("Vault backend")),
        FieldSet("api_url", "secret_engine", "default_namespace", "azure_api_version", name=_("Provider configuration")),
        FieldSet("description", "extra_config", name=_("Additional data")),
    )

    class Meta:
        model = VaultBackend
        fields = (
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
        )

    def clean(self):
        cleaned_data = super().clean() or self.cleaned_data
        if cleaned_data.get("extra_config") is None:
            cleaned_data["extra_config"] = {}
        if cleaned_data.get("backend_type") == VaultBackendTypeChoices.HASHICORP and not cleaned_data.get("secret_engine"):
            self.add_error("secret_engine", _("HashiCorp Vault requires a secret engine mount path."))
        return cleaned_data


class VaultSecretForm(NetBoxModelForm):
    fieldsets = (
        FieldSet("name", "vault_backend", "enabled", name=_("Secret")),
        FieldSet("secret_path", "secret_key", "refresh_interval_hours", name=_("Vault mapping")),
        FieldSet("description", name=_("Notes")),
    )

    class Meta:
        model = VaultSecret
        fields = ("name", "vault_backend", "secret_path", "secret_key", "refresh_interval_hours", "enabled", "description")


class VaultSecretValueForm(forms.Form):
    value = forms.CharField(
        label=_("New secret value"),
        widget=forms.PasswordInput(render_value=False),
        strip=False,
        help_text=_("The plaintext value is sent to the vault and is never shown again by the UI."),
    )


class VaultBackendFilterForm(NetBoxModelFilterSetForm):
    model = VaultBackend
    name = forms.CharField(required=False)
    backend_type = forms.MultipleChoiceField(choices=VaultBackendTypeChoices.choices, required=False)
    enabled = forms.ChoiceField(choices=BOOLEAN_CHOICES, required=False)


class VaultSecretFilterForm(NetBoxModelFilterSetForm):
    model = VaultSecret
    name = forms.CharField(required=False)
    vault_backend_id = forms.ModelMultipleChoiceField(queryset=VaultBackend.objects.all(), required=False)
    last_refresh_status = forms.MultipleChoiceField(choices=VaultSecret._meta.get_field("last_refresh_status").choices, required=False)
    enabled = forms.ChoiceField(choices=BOOLEAN_CHOICES, required=False)
