import { test, expect } from '@playwright/test';
import { createApiContext, deleteBackendByName, getPlainValueThroughService, uniqueName } from './helpers/netbox.js';
import { putAwsSecret } from './helpers/vault.js';

const backendApi = '/api/plugins/vault/vault-backends/';
const secretApi = '/api/plugins/vault/vault-secrets/';

test('AWS Secrets Manager emulator API refresh flow', async ({ page }) => {
  const api = await createApiContext(page);
  const backendName = uniqueName('AWS Backend');
  await deleteBackendByName(api, backendApi, backendName);

  const backendResponse = await api.post(backendApi, {
    data: {
      name: backendName,
      backend_type: 'aws_secrets_manager',
      api_url: 'http://aws-secrets.test:5000',
      secret_engine: '',
      default_namespace: '',
      azure_api_version: '7.5',
      enabled: true,
      description: 'AWS backend for emulator tests',
      extra_config: { credentials_key: 'aws-test' },
    },
  });
  expect(backendResponse.ok()).toBeTruthy();
  const backend = await backendResponse.json();

  const externalSecretName = `aws-secret-${Date.now()}`;
  await putAwsSecret(externalSecretName, 'aws-initial-value');

  const secretName = uniqueName('aws-secret');
  const createSecretResponse = await api.post(secretApi, {
    data: {
      name: secretName,
      vault_backend_id: backend.id,
      secret_path: externalSecretName,
      secret_key: 'value',
      refresh_interval_hours: 1,
      enabled: true,
      description: 'AWS secret',
    },
  });
  expect(createSecretResponse.ok()).toBeTruthy();
  const createdSecret = await createSecretResponse.json();

  const refreshResponse = await api.post(`${secretApi}${createdSecret.id}/refresh/`);
  expect(refreshResponse.ok()).toBeTruthy();
  const refreshed = await refreshResponse.json();
  expect(refreshed.last_refresh_status).toBe('synced');
  expect(getPlainValueThroughService(secretName)).toContain('aws-initial-value');

  const deleteSecretResponse = await api.delete(`${secretApi}${createdSecret.id}/`);
  expect(deleteSecretResponse.status()).toBe(204);
  const deleteBackendResponse = await api.delete(`${backendApi}${backend.id}/`);
  expect(deleteBackendResponse.status()).toBe(204);
});
