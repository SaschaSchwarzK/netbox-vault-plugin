from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import uuid

from django.conf import settings
from django.core.cache import caches
from netbox.plugins import get_plugin_config
import redis
from redis.exceptions import RedisError
from redis.sentinel import Sentinel

from .crypto import SecretDecryptionError, decrypt_value, encrypt_value

logger = logging.getLogger(__name__)


class SecretCacheUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class CachedSecretPayload:
    ciphertext: str
    refreshed_at: str | None = None
    status: str | None = None
    version: int = 1


def _plugin_setting(name, default=None):
    try:
        return get_plugin_config("netbox_vault", name)
    except Exception:
        return default


def _get_cache_location() -> str | None:
    cache_config = settings.CACHES.get("default", {})
    location = cache_config.get("LOCATION")
    if isinstance(location, (list, tuple)):
        return location[0] if location else None
    return location


def get_redis_url() -> str | None:
    return _plugin_setting("redis_url") or _get_cache_location()


def _build_netbox_redis_client() -> redis.Redis | None:
    redis_config = getattr(settings, "REDIS", {}).get("caching")
    if not redis_config:
        return None

    sentinels = redis_config.get("SENTINELS") or []
    if sentinels:
        sentinel = Sentinel(
            sentinels,
            socket_timeout=redis_config.get("SENTINEL_TIMEOUT", 10),
            username=redis_config.get("USERNAME") or None,
            password=redis_config.get("PASSWORD") or None,
            ssl=bool(redis_config.get("SSL")),
        )
        return sentinel.master_for(
            redis_config.get("SENTINEL_SERVICE", "default"),
            db=redis_config.get("DATABASE", 0),
            username=redis_config.get("USERNAME") or None,
            password=redis_config.get("PASSWORD") or None,
            ssl=bool(redis_config.get("SSL")),
            decode_responses=True,
        )

    return redis.Redis(
        host=redis_config.get("HOST", "localhost"),
        port=redis_config.get("PORT", 6379),
        db=redis_config.get("DATABASE", 0),
        username=redis_config.get("USERNAME") or None,
        password=redis_config.get("PASSWORD") or None,
        ssl=bool(redis_config.get("SSL")),
        decode_responses=True,
    )


def _get_default_cache_redis_client() -> redis.Redis | None:
    cache_backend = caches["default"]
    client = getattr(cache_backend, "client", None)
    get_client = getattr(client, "get_client", None)
    if callable(get_client):
        try:
            return get_client(write=True)
        except TypeError:
            return get_client()
    return None


def get_redis_client() -> redis.Redis:
    configured_url = _plugin_setting("redis_url")
    if configured_url:
        return redis.Redis.from_url(configured_url, decode_responses=True)

    netbox_client = _build_netbox_redis_client()
    if netbox_client is not None:
        return netbox_client

    cache_client = _get_default_cache_redis_client()
    if cache_client is not None:
        return cache_client

    redis_url = get_redis_url()
    if not redis_url:
        raise SecretCacheUnavailableError(
            "No Redis cache is configured for netbox_vault. Set PLUGINS_CONFIG['netbox_vault']['redis_url'] or use NetBox's Redis cache configuration."
        )
    return redis.Redis.from_url(redis_url, decode_responses=True)


def get_cache_key(secret) -> str:
    prefix = (_plugin_setting("redis_key_prefix", "netbox_vault") or "netbox_vault").strip(":")
    return f"{prefix}:secret:{secret.pk}"


def get_startup_lock_key() -> str:
    prefix = (_plugin_setting("redis_key_prefix", "netbox_vault") or "netbox_vault").strip(":")
    return f"{prefix}:startup-sync-lock"


def get_startup_marker_key() -> str:
    prefix = (_plugin_setting("redis_key_prefix", "netbox_vault") or "netbox_vault").strip(":")
    return f"{prefix}:startup-sync-done"


def has_cached_secret(secret) -> bool:
    try:
        return bool(get_redis_client().exists(get_cache_key(secret)))
    except RedisError as exc:
        raise SecretCacheUnavailableError("Unable to inspect the Redis-backed secret cache.") from exc


def read_cached_secret_payload(secret) -> CachedSecretPayload | None:
    try:
        raw_payload = get_redis_client().get(get_cache_key(secret))
    except RedisError as exc:
        raise SecretCacheUnavailableError("Unable to read from the Redis-backed secret cache.") from exc

    if not raw_payload:
        return None

    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return CachedSecretPayload(ciphertext=raw_payload)

    return CachedSecretPayload(
        ciphertext=payload["ciphertext"],
        refreshed_at=payload.get("refreshed_at"),
        status=payload.get("status"),
        version=payload.get("version", 1),
    )


def write_cached_secret(secret, plaintext: str):
    payload = {
        "version": 1,
        "ciphertext": encrypt_value(plaintext),
        "refreshed_at": secret.last_refreshed.isoformat() if secret.last_refreshed else None,
        "status": secret.last_refresh_status,
    }
    try:
        get_redis_client().set(get_cache_key(secret), json.dumps(payload))
    except RedisError as exc:
        raise SecretCacheUnavailableError("Unable to write to the Redis-backed secret cache.") from exc
    return payload


def delete_cached_secret(secret):
    try:
        get_redis_client().delete(get_cache_key(secret))
    except RedisError as exc:
        raise SecretCacheUnavailableError("Unable to delete from the Redis-backed secret cache.") from exc


def get_cached_secret_value(secret) -> str:
    payload = read_cached_secret_payload(secret)
    if payload is None:
        raise SecretDecryptionError(f"Secret '{secret.name}' has no cached value.")
    return decrypt_value(payload.ciphertext)


def acquire_startup_sync_lock() -> str | None:
    lock_token = uuid.uuid4().hex
    ttl = int(_plugin_setting("startup_sync_lock_ttl", 300) or 300)
    try:
        acquired = get_redis_client().set(get_startup_lock_key(), lock_token, nx=True, ex=ttl)
    except RedisError as exc:
        raise SecretCacheUnavailableError("Unable to acquire the Redis startup sync lock.") from exc
    return lock_token if acquired else None


def release_startup_sync_lock(lock_token: str):
    client = get_redis_client()
    lock_key = get_startup_lock_key()
    try:
        if client.get(lock_key) == lock_token:
            client.delete(lock_key)
    except RedisError:
        logger.warning("Failed to release startup sync lock for netbox_vault.", exc_info=True)


def startup_sync_completed_recently() -> bool:
    try:
        return bool(get_redis_client().exists(get_startup_marker_key()))
    except RedisError as exc:
        raise SecretCacheUnavailableError("Unable to inspect the Redis startup sync marker.") from exc


def mark_startup_sync_completed():
    ttl = int(_plugin_setting("startup_sync_marker_ttl", 600) or 600)
    try:
        get_redis_client().set(get_startup_marker_key(), "1", ex=ttl)
    except RedisError as exc:
        raise SecretCacheUnavailableError("Unable to write the Redis startup sync marker.") from exc
