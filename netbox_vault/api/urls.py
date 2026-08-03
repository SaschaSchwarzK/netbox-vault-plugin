from netbox.api.routers import NetBoxRouter

from . import views

app_name = "netbox_vault"

router = NetBoxRouter()
router.register("vault-backends", views.VaultBackendViewSet)
router.register("vault-secrets", views.VaultSecretViewSet)

urlpatterns = router.urls
