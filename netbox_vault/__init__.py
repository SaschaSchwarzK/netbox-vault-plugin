import logging
import sys
import threading

from netbox.plugins import PluginConfig, get_plugin_config

logger = logging.getLogger(__name__)


class NetBoxVaultConfig(PluginConfig):
    name = "netbox_vault"
    verbose_name = "NetBox Vault"
    description = "Synchronize vault-backed secrets into an encrypted NetBox cache"
    version = "0.1.0"
    author = "Sascha"
    base_url = "vault"
    min_version = "4.4.0"
    default_settings = {
        "backend_credentials": {},
        "redis_key_prefix": "netbox_vault",
        "redis_url": None,
        "request_timeout": 15,
        "startup_sync_enabled": False,
        "startup_sync_lock_ttl": 300,
        "startup_sync_marker_ttl": 600,
    }

    def ready(self):
        super().ready()
        from .jobs import RefreshDueVaultSecretsJob  # noqa: F401
        from . import signals  # noqa: F401

        if "test" in sys.argv:
            return

        try:
            startup_sync_enabled = bool(get_plugin_config("netbox_vault", "startup_sync_enabled"))
        except Exception:
            startup_sync_enabled = False

        if not startup_sync_enabled:
            return

        from .secrets import run_startup_secret_sync

        def _run_sync():
            try:
                run_startup_secret_sync()
            except Exception:
                logger.warning("netbox_vault startup sync failed.", exc_info=True)

        threading.Thread(target=_run_sync, name="netbox-vault-startup-sync", daemon=True).start()


config = NetBoxVaultConfig
