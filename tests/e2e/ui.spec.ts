import { test, expect } from '@playwright/test';
import {
  createApiContext,
  expectVaultMenuVisible,
  gotoVaultBackendAdd,
  gotoVaultSecretAdd,
  triggerRefreshAllSecrets,
  uniqueName,
} from './helpers/netbox.js';
import { getBackendPayload, type BackendKind } from './helpers/backend-fixtures.js';
import { putAwsSecret, putAzureSecret, putGoogleSecret, putHashicorpSecret } from './helpers/vault.js';

const backendListUrl = '/plugins/vault/vault-backends/';
const secretListUrl = '/plugins/vault/secrets/';
const backendApi = '/api/plugins/vault/vault-backends/';
const secretApi = '/api/plugins/vault/vault-secrets/';

const backendConfigs: Array<{
  apiUrl?: string;
  backendType: BackendKind;
  credentials: string;
  externalSecretName: () => string;
  seed: (name: string, value: string) => Promise<void>;
}> = [
  {
    backendType: 'hashicorp',
    credentials: '{"credentials_key":"hashicorp-test"}',
    externalSecretName: () => `ui/hashicorp/${Date.now()}`,
    seed: (name, value) => putHashicorpSecret(name, 'value', value),
  },
  {
    backendType: 'azure_key_vault',
    credentials: '{"verify_tls":false,"credentials_key":"azure-test"}',
    externalSecretName: () => `azure-ui-${Date.now()}`,
    seed: (name, value) => putAzureSecret(name, value),
  },
  {
    backendType: 'google_cloud_secret_manager',
    credentials: '{"credentials_key":"gcp-test"}',
    externalSecretName: () => `gcp-ui-${Date.now()}`,
    seed: (name, value) => putGoogleSecret(name, value),
  },
  {
    backendType: 'aws_secrets_manager',
    credentials: '{"credentials_key":"aws-test"}',
    externalSecretName: () => `aws-ui-${Date.now()}`,
    seed: (name, value) => putAwsSecret(name, value),
  },
];

for (const config of backendConfigs) {
  test(`UI CRUD and manual refresh for ${config.backendType}`, async ({ page }) => {
    const api = await createApiContext(page);
    const backendName = uniqueName(`UI ${config.backendType} backend`);
    const secretName = uniqueName(`UI ${config.backendType} secret`);
    const externalSecretName = config.externalSecretName();
    const plainValue = `${config.backendType}-ui-value-${Date.now()}`;

    await config.seed(externalSecretName, plainValue);

    const backendPayload = getBackendPayload(config.backendType, backendName);
    await page.goto(backendListUrl);
    await expectVaultMenuVisible(page);
    await gotoVaultBackendAdd(page);
    await page.locator('#id_name').fill(backendName);
    await page.locator('#id_backend_type').selectOption(config.backendType);
    await page.locator('#id_api_url').fill(String(backendPayload.api_url ?? ''));
    await page.locator('#id_secret_engine').fill(String(backendPayload.secret_engine ?? ''));
    await page.locator('#id_default_namespace').fill(String(backendPayload.default_namespace ?? ''));
    await page.locator('#id_azure_api_version').fill(String(backendPayload.azure_api_version ?? '7.5'));
    await page.locator('#id_extra_config').fill(config.credentials);
    await page.getByLabel('Description').fill(`Created through the ${config.backendType} UI test`);
    await page.getByRole('button', { name: /^Create$/ }).click();
    await expect(page.getByRole('cell', { name: backendName })).toBeVisible();

    await page.getByRole('link', { name: backendName }).click();
    await page.getByRole('button', { name: /edit|bearbeiten/i }).click();
    await page.getByLabel('Description').fill(`Edited through the ${config.backendType} UI test`);
    await page.getByRole('button', { name: /^Save$/ }).click();
    await expect(page.getByText(`Edited through the ${config.backendType} UI test`)).toBeVisible();

    await page.goto(secretListUrl);
    await gotoVaultSecretAdd(page);
    await page.locator('#id_name').fill(secretName);
    await page.locator('#id_vault_backend').selectOption({ label: backendName });
    await page.getByLabel('Secret path').fill(externalSecretName);
    await page.getByLabel('Secret key').fill('value');
    await page.getByLabel('Refresh interval hours').fill('1');
    await page.getByRole('button', { name: /^Create$/ }).click();
    await expect(page.getByRole('cell', { name: secretName })).toBeVisible();

    await page.getByRole('link', { name: secretName }).click();
    await page.getByRole('button', { name: /refresh now/i }).click();
    await expect(page.getByText(/secret refreshed successfully/i)).toBeVisible();
    await expect(page.getByText(/synced/i)).toBeVisible();

    await page.getByRole('button', { name: /edit|bearbeiten/i }).click();
    await page.getByLabel('Refresh interval hours').fill('2');
    await page.getByLabel('Description').fill(`Edited ${config.backendType} secret`);
    await page.getByRole('button', { name: /^Save$/ }).click();
    await expect(page.locator('body')).toContainText('2h');
    await expect(page.locator('body')).toContainText(/synced|synchronisiert/i);

    await page.getByRole('button', { name: /delete|löschen/i }).click();
    await page.locator('#htmx-modal-content').getByRole('button', { name: /delete|löschen/i }).click();
    await expect(page).toHaveURL(/\/plugins\/vault\/secrets\/?$/);

    await page.goto(backendListUrl);
    await page.getByRole('link', { name: backendName }).click();
    await page.getByRole('button', { name: /delete|löschen/i }).click();
    await page.locator('#htmx-modal-content').getByRole('button', { name: /delete|löschen/i }).click();
    await expect(page).toHaveURL(/\/plugins\/vault\/vault-backends\/?$/);

    const backendListResponse = await api.get(`${backendApi}?name=${encodeURIComponent(backendName)}`);
    const backendList = await backendListResponse.json();
    expect(backendList.results).toHaveLength(0);
    const secretListResponse = await api.get(`${secretApi}?name=${encodeURIComponent(secretName)}`);
    const secretList = await secretListResponse.json();
    expect(secretList.results).toHaveLength(0);
  });
}

test('UI refresh-all action refreshes all cached secrets', async ({ page }) => {
  const api = await createApiContext(page);
  const backendName = uniqueName('UI refresh all backend');
  const backendResponse = await api.post(backendApi, {
    data: getBackendPayload('hashicorp', backendName),
  });
  expect(backendResponse.ok()).toBeTruthy();
  const backend = await backendResponse.json();

  const fixtures = [
    { name: uniqueName('refresh-all-secret-a'), path: `ui/refresh-all/${Date.now()}/a`, value: `refresh-all-a-${Date.now()}`, id: 0 },
    { name: uniqueName('refresh-all-secret-b'), path: `ui/refresh-all/${Date.now()}/b`, value: `refresh-all-b-${Date.now()}`, id: 0 },
  ];

  for (const fixture of fixtures) {
    await putHashicorpSecret(fixture.path, 'value', fixture.value);
    const response = await api.post(secretApi, {
      data: {
        name: fixture.name,
        vault_backend_id: backend.id,
        secret_path: fixture.path,
        secret_key: 'value',
        refresh_interval_hours: 1,
        enabled: true,
        description: 'Refresh-all UI fixture',
      },
    });
    expect(response.ok()).toBeTruthy();
    fixture.id = (await response.json()).id;
  }

  try {
    await page.goto(secretListUrl);
    await triggerRefreshAllSecrets(page);
    await expect(page).toHaveURL(/\/plugins\/vault\/secrets\/?$/);

    for (const fixture of fixtures) {
      await expect.poll(async () => {
        const detail = await (await api.get(`${secretApi}${fixture.id}/`)).json();
        return `${detail.last_refresh_status}:${detail.last_refreshed ? 'yes' : 'no'}`;
      }).toBe('synced:yes');
    }
  } finally {
    const secrets = await (await api.get(`${secretApi}?vault_backend_id=${backend.id}`)).json();
    for (const result of secrets.results ?? []) {
      await api.delete(`${secretApi}${result.id}/`);
    }
    await api.delete(`${backendApi}${backend.id}/`);
  }
});
