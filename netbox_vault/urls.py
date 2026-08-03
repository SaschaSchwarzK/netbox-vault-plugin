from django.urls import path

from netbox.views import generic

from . import models, views

app_name = "netbox_vault"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("vault-backends/", views.VaultBackendListView.as_view(), name="vaultbackend_list"),
    path("vault-backends/add/", views.VaultBackendEditView.as_view(), name="vaultbackend_add"),
    path("vault-backends/<int:pk>/", views.VaultBackendView.as_view(), name="vaultbackend"),
    path("vault-backends/<int:pk>/edit/", views.VaultBackendEditView.as_view(), name="vaultbackend_edit"),
    path("vault-backends/<int:pk>/delete/", views.VaultBackendDeleteView.as_view(), name="vaultbackend_delete"),
    path(
        "vault-backends/<int:pk>/changelog/",
        generic.ObjectChangeLogView.as_view(),
        {"model": models.VaultBackend},
        name="vaultbackend_changelog",
    ),
    path("secrets/", views.VaultSecretListView.as_view(), name="vaultsecret_list"),
    path("secrets/add/", views.VaultSecretEditView.as_view(), name="vaultsecret_add"),
    path("secrets/refresh/", views.RefreshAllSecretsView.as_view(), name="vaultsecret_refresh_all"),
    path("secrets/<int:pk>/", views.VaultSecretView.as_view(), name="vaultsecret"),
    path("secrets/<int:pk>/edit/", views.VaultSecretEditView.as_view(), name="vaultsecret_edit"),
    path("secrets/<int:pk>/delete/", views.VaultSecretDeleteView.as_view(), name="vaultsecret_delete"),
    path(
        "secrets/<int:pk>/changelog/",
        generic.ObjectChangeLogView.as_view(),
        {"model": models.VaultSecret},
        name="vaultsecret_changelog",
    ),
    path("secrets/<int:pk>/refresh/", views.RefreshSecretView.as_view(), name="vaultsecret_refresh"),
]
