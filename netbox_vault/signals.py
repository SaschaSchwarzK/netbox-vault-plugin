from django.db.models.signals import post_delete
from django.dispatch import receiver

from .cache import SecretCacheUnavailableError, delete_cached_secret
from .models import VaultSecret


@receiver(post_delete, sender=VaultSecret)
def purge_secret_cache_on_delete(sender, instance, **kwargs):
    try:
        delete_cached_secret(instance)
    except SecretCacheUnavailableError:
        pass
