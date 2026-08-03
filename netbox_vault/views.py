from django.contrib import messages
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import RedirectView

from netbox.views import generic
from utilities.views import register_model_view

from . import filtersets, forms, models, tables
from .secrets import refresh_all_secrets, refresh_secret


class HomeView(RedirectView):
    pattern_name = "plugins:netbox_vault:vaultsecret_list"


@register_model_view(models.VaultBackend)
class VaultBackendView(generic.ObjectView):
    queryset = models.VaultBackend.objects.all()
    template_name = "netbox_vault/vaultbackend.html"


@register_model_view(models.VaultBackend, name="list", path="", detail=False)
class VaultBackendListView(generic.ObjectListView):
    queryset = models.VaultBackend.objects.all()
    table = tables.VaultBackendTable
    filterset = filtersets.VaultBackendFilterSet
    filterset_form = forms.VaultBackendFilterForm


@register_model_view(models.VaultBackend, name="add", detail=False)
@register_model_view(models.VaultBackend, name="edit")
class VaultBackendEditView(generic.ObjectEditView):
    queryset = models.VaultBackend.objects.all()
    form = forms.VaultBackendForm


@register_model_view(models.VaultBackend, name="delete")
class VaultBackendDeleteView(generic.ObjectDeleteView):
    queryset = models.VaultBackend.objects.all()


@register_model_view(models.VaultSecret)
class VaultSecretView(generic.ObjectView):
    queryset = models.VaultSecret.objects.select_related("vault_backend")
    template_name = "netbox_vault/vaultsecret.html"


@register_model_view(models.VaultSecret, name="list", path="", detail=False)
class VaultSecretListView(generic.ObjectListView):
    queryset = models.VaultSecret.objects.select_related("vault_backend")
    table = tables.VaultSecretTable
    filterset = filtersets.VaultSecretFilterSet
    filterset_form = forms.VaultSecretFilterForm


@register_model_view(models.VaultSecret, name="add", detail=False)
@register_model_view(models.VaultSecret, name="edit")
class VaultSecretEditView(generic.ObjectEditView):
    queryset = models.VaultSecret.objects.select_related("vault_backend")
    form = forms.VaultSecretForm


@register_model_view(models.VaultSecret, name="delete")
class VaultSecretDeleteView(generic.ObjectDeleteView):
    queryset = models.VaultSecret.objects.select_related("vault_backend")


class RefreshSecretView(View):
    def post(self, request, pk):
        if not request.user.has_perm("netbox_vault.change_vaultsecret"):
            return HttpResponseForbidden()

        secret = get_object_or_404(models.VaultSecret.objects.select_related("vault_backend"), pk=pk)
        try:
            refresh_secret(secret)
            messages.success(request, _("Secret refreshed successfully."))
        except Exception as exc:
            messages.error(request, _("Secret refresh failed: %(error)s") % {"error": exc})
        return redirect(secret.get_absolute_url())


class RefreshAllSecretsView(View):
    def get(self, request):
        return self._refresh(request)

    def post(self, request):
        return self._refresh(request)

    def _refresh(self, request):
        if not request.user.has_perm("netbox_vault.change_vaultsecret"):
            return HttpResponseForbidden()

        refreshed, failures = refresh_all_secrets(due_only=False, raise_on_failure=False)
        if refreshed:
            messages.success(
                request,
                _("Refreshed %(count)s secret(s).") % {"count": len(refreshed)},
            )
        if failures:
            messages.warning(
                request,
                _("%(count)s secret(s) failed to refresh. Check each secret for details.")
                % {"count": len(failures)},
            )
        if not refreshed and not failures:
            messages.info(request, _("No enabled secrets were available to refresh."))
        return redirect(reverse("plugins:netbox_vault:vaultsecret_list"))
