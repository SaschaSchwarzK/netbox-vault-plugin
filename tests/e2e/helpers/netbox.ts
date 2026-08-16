import { APIRequestContext, Locator, Page, expect, request } from '@playwright/test';
import { adminPassword, adminUser, netboxBaseUrl } from './config.js';
import { netboxShell } from './docker.js';

type PermissionSpec = {
  actions: string[];
  constraints?: Record<string, unknown> | Array<Record<string, unknown>>;
  description?: string;
  name: string;
  objectTypes: string[];
};

type UserFixtureSpec = {
  email?: string;
  password: string;
  permissions: PermissionSpec[];
  username: string;
};

export async function login(page: Page) {
  await loginAs(page, adminUser, adminPassword);
}

export async function loginAs(page: Page, username: string, password: string) {
  await page.goto('/login/');
  await page.getByLabel('Username').fill(username);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: /log in|sign in/i }).click();
  await expect(page).toHaveURL(/\/home\/|\/$/);
}

export async function createApiContext(page: Page): Promise<APIRequestContext> {
  const storageState = await page.context().storageState();
  const csrfToken = storageState.cookies.find((cookie) => cookie.name === 'csrftoken')?.value;

  return request.newContext({
    baseURL: netboxBaseUrl,
    storageState,
    extraHTTPHeaders: {
      Accept: 'application/json',
      ...(csrfToken ? { 'X-CSRFToken': csrfToken, Referer: `${netboxBaseUrl}/` } : {}),
    },
    ignoreHTTPSErrors: true,
  });
}

export function vaultMenuButton(page: Page): Locator {
  return page.getByRole('button', { name: /^Vault(?:\s|$)/i });
}

export async function expectVaultMenuVisible(page: Page) {
  await expect(vaultMenuButton(page)).toBeVisible();
}

export async function expectVaultMenuHidden(page: Page) {
  await expect(vaultMenuButton(page)).toHaveCount(0);
}

export async function gotoVaultBackendAdd(page: Page) {
  await page.goto('/plugins/vault/vault-backends/add/');
  await expect(page.locator('#id_name')).toBeVisible();
}

export async function gotoVaultSecretAdd(page: Page) {
  await page.goto('/plugins/vault/secrets/add/');
  await expect(page.locator('#id_name')).toBeVisible();
}

export async function triggerRefreshAllSecrets(page: Page) {
  await page.goto('/plugins/vault/secrets/refresh/');
}

export function deleteBackendByName(api: APIRequestContext, backendApi: string, name: string) {
  return api.get(`${backendApi}?name=${encodeURIComponent(name)}`).then(async (existing) => {
    if (!existing.ok()) {
      return;
    }
    const payload = await existing.json();
    for (const result of payload.results ?? []) {
      await api.delete(`${backendApi}${result.id}/`);
    }
  });
}

export function uniqueName(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;
}

export function getEncryptedValue(name: string) {
  return netboxShell(`from netbox_vault.cache import read_cached_secret_payload\nfrom netbox_vault.models import VaultSecret\nsecret = VaultSecret.objects.get(name=${JSON.stringify(name)})\npayload = read_cached_secret_payload(secret)\nprint(payload.ciphertext if payload else '')`);
}

export function databaseStoresSecretValue(name: string) {
  return netboxShell(`from netbox_vault.models import VaultSecret\nsecret = VaultSecret.objects.get(name=${JSON.stringify(name)})\nprint(hasattr(secret, 'encrypted_value'))`);
}

export function getPlainValueThroughService(name: string) {
  return netboxShell(`from netbox_vault.secrets import get_secret_value; print(get_secret_value(${JSON.stringify(name)}))`);
}

export function markSecretDue(name: string) {
  return netboxShell(
    `from datetime import timedelta; from django.utils import timezone; from netbox_vault.models import VaultSecret; secret = VaultSecret.objects.get(name=${JSON.stringify(name)}); secret.last_refreshed = timezone.now() - timedelta(hours=secret.refresh_interval_hours + 1); secret.save(update_fields=('last_refreshed','last_updated')); print('ok')`
  );
}

export function markSecretFresh(name: string) {
  return netboxShell(
    `from django.utils import timezone; from netbox_vault.models import VaultSecret; secret = VaultSecret.objects.get(name=${JSON.stringify(name)}); secret.last_refreshed = timezone.now(); secret.save(update_fields=('last_refreshed','last_updated')); print('ok')`
  );
}

export function ensureUserFixture(spec: UserFixtureSpec) {
  const payload = JSON.stringify(spec);
  return netboxShell(`import json
from django.contrib.contenttypes.models import ContentType
from users.models import ObjectPermission, User
spec = json.loads(${JSON.stringify(payload)})
user, _ = User.objects.get_or_create(username=spec['username'])
user.email = spec.get('email', '')
user.is_active = True
user.is_superuser = False
user.set_password(spec['password'])
user.save()
user.object_permissions.clear()
for perm_spec in spec['permissions']:
    perm, _ = ObjectPermission.objects.update_or_create(
        name=perm_spec['name'],
        defaults={
            'description': perm_spec.get('description', ''),
            'enabled': True,
            'actions': perm_spec['actions'],
            'constraints': perm_spec.get('constraints') or {},
        },
    )
    object_types = []
    for object_type in perm_spec['objectTypes']:
        app_label, model = object_type.split('.', 1)
        object_types.append(ContentType.objects.get(app_label=app_label, model=model))
    perm.object_types.set(object_types)
    user.object_permissions.add(perm)
print('ok')`);
}

export function removeUserFixture(username: string) {
  return netboxShell(`from users.models import User
User.objects.filter(username=${JSON.stringify(username)}).delete()
print('ok')`);
}
