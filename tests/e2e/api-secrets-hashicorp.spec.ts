import { test, expect } from '@playwright/test';
import { createApiContext, databaseStoresSecretValue, deleteBackendByName, getEncryptedValue, getPlainValueThroughService, markSecretDue, markSecretFresh, uniqueName } from './helpers/netbox.js';
import { putHashicorpSecret } from './helpers/vault.js';
import { netboxManage, netboxShell } from './helpers/docker.js';

const backendApi = '/api/plugins/vault/vault-backends/';
const secretApi = '/api/plugins/vault/vault-secrets/';

test('HashiCorp API CRUD and refresh flows', async ({ page }) => {
  const api = await createApiContext(page);

  const backendName = uniqueName('hashicorp-test');
  await deleteBackendByName(api, backendApi, backendName);

  const backendResponse = await api.post(backendApi, {
    data: {
      name: backendName,
      backend_type: 'hashicorp',
      api_url: 'http://vault.test:8200',
      secret_engine: 'secret',
      default_namespace: '',
      azure_api_version: '7.5',
      enabled: true,
      description: 'HashiCorp backend for API tests',
      extra_config: { credentials_key: 'hashicorp-test' },
    },
  });
  expect(backendResponse.ok()).toBeTruthy();
  const backend = await backendResponse.json();

  const externalSecretPath = `playwright/${Date.now()}`;
  await putHashicorpSecret(externalSecretPath, 'value', 'hashi-initial-value');

  const secretName = uniqueName('hashi-secret');
  const createSecretResponse = await api.post(secretApi, {
    data: {
      name: secretName,
      vault_backend_id: backend.id,
      secret_path: externalSecretPath,
      secret_key: 'value',
      refresh_interval_hours: 1,
      enabled: true,
      description: 'HashiCorp secret',
    },
  });
  expect(createSecretResponse.ok()).toBeTruthy();
  const createdSecret = await createSecretResponse.json();

  const refreshResponse = await api.post(`${secretApi}${createdSecret.id}/refresh/`);
  expect(refreshResponse.ok()).toBeTruthy();
  const refreshedSecret = await refreshResponse.json();
  expect(refreshedSecret.last_refresh_status).toBe('synced');
  expect(refreshedSecret.has_cached_value).toBe(true);

  const encryptedValue = getEncryptedValue(secretName);
  expect(encryptedValue).not.toContain('hashi-initial-value');
  expect(getPlainValueThroughService(secretName)).toContain('hashi-initial-value');
  expect(databaseStoresSecretValue(secretName)).toContain('False');

  await putHashicorpSecret(externalSecretPath, 'value', 'hashi-updated-value');
  netboxShell(`from django.utils import timezone
from netbox_vault.models import VaultSecret
VaultSecret.objects.exclude(name=${JSON.stringify(secretName)}).update(last_refreshed=timezone.now())
print('ok')`);
  markSecretDue(secretName);
  netboxManage('refresh_vault_secrets', '--due-only');
  expect(getPlainValueThroughService(secretName)).toContain('hashi-updated-value');

  await putHashicorpSecret(externalSecretPath, 'value', 'hashi-still-fresh-value');
  netboxShell(`from django.utils import timezone
from netbox_vault.models import VaultSecret
VaultSecret.objects.update(last_refreshed=timezone.now())
print('ok')`);

  const freshBeforeResponse = await api.get(`${secretApi}${createdSecret.id}/`);
  expect(freshBeforeResponse.ok()).toBeTruthy();
  const freshBefore = await freshBeforeResponse.json();
  expect(freshBefore.is_refresh_due).toBe(false);

  const dueOnlyOutput = netboxManage('refresh_vault_secrets', '--due-only');
  expect(dueOnlyOutput).not.toContain(`Refreshed ${secretName}`);

  const freshAfterResponse = await api.get(`${secretApi}${createdSecret.id}/`);
  expect(freshAfterResponse.ok()).toBeTruthy();
  const freshAfter = await freshAfterResponse.json();
  expect(freshAfter.is_refresh_due).toBe(false);

  const patchResponse = await api.patch(`${secretApi}${createdSecret.id}/`, {
    data: {
      description: 'Updated secret description',
      refresh_interval_hours: 2,
    },
  });
  expect(patchResponse.ok()).toBeTruthy();

  const refreshAllResponse = await api.post(`${secretApi}refresh-all/`, {
    data: { due_only: false },
  });
  expect(refreshAllResponse.ok()).toBeTruthy();
  const refreshAllData = await refreshAllResponse.json();
  expect(refreshAllData.refreshed).toContain(secretName);

  const deleteSecretResponse = await api.delete(`${secretApi}${createdSecret.id}/`);
  expect(deleteSecretResponse.status()).toBe(204);
  const deleteBackendResponse = await api.delete(`${backendApi}${backend.id}/`);
  expect(deleteBackendResponse.status()).toBe(204);
});
