import { test, expect } from '@playwright/test';
import { cleanupSecretFixture, createSecretFixture, refreshFixture } from './helpers/backend-fixtures.js';
import { createApiContext, ensureUserFixture, loginAs, removeUserFixture, uniqueName } from './helpers/netbox.js';

const backendListUrl = '/plugins/vault/vault-backends/';
const secretListUrl = '/plugins/vault/secrets/';
const backendApi = '/api/plugins/vault/vault-backends/';
const secretApi = '/api/plugins/vault/vault-secrets/';

test('RBAC hides vault menu and denies access without permissions', async ({ browser, page }) => {
  const api = await createApiContext(page);
  const fixture = await createSecretFixture(api, 'hashicorp');
  await refreshFixture(api, fixture.secretId);

  const username = uniqueName('vault-noperms').replace(/[^a-z0-9]/gi, '').toLowerCase();
  const password = 'VaultRbac123!';

  try {
    ensureUserFixture({ username, password, permissions: [] });
    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const userPage = await context.newPage();
    await loginAs(userPage, username, password);
    await expect(userPage.getByRole('button', { name: /^Vault$/i })).toHaveCount(0);

    const backendResponse = await userPage.goto(backendListUrl);
    expect(backendResponse?.status()).toBe(403);
    const secretResponse = await userPage.goto(secretListUrl);
    expect(secretResponse?.status()).toBe(403);
    await context.close();
  } finally {
    removeUserFixture(username);
    await cleanupSecretFixture(api, fixture);
  }
});

test('RBAC enforces view-only access for vault models in UI and API', async ({ browser, page }) => {
  const adminApi = await createApiContext(page);
  const fixture = await createSecretFixture(adminApi, 'hashicorp');
  await refreshFixture(adminApi, fixture.secretId);

  const username = uniqueName('vault-view').replace(/[^a-z0-9]/gi, '').toLowerCase();
  const password = 'VaultRbac123!';

  try {
    ensureUserFixture({
      username,
      password,
      permissions: [
        {
          name: `${username}-view-backends`,
          objectTypes: ['netbox_vault.vaultbackend'],
          actions: ['view'],
        },
        {
          name: `${username}-view-secrets`,
          objectTypes: ['netbox_vault.vaultsecret'],
          actions: ['view'],
        },
      ],
    });

    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const userPage = await context.newPage();
    await loginAs(userPage, username, password);
    await expect(userPage.getByRole('button', { name: /^Vault$/i })).toBeVisible();

    await userPage.goto(backendListUrl);
    await expect(userPage.getByText(fixture.backendName)).toBeVisible();
    await expect(userPage.getByRole('link', { name: /add vault backend/i })).toHaveCount(0);

    await userPage.goto(secretListUrl);
    await expect(userPage.getByText(fixture.secretName)).toBeVisible();
    await expect(userPage.getByRole('link', { name: /add vault secret/i })).toHaveCount(0);

    const userApi = await createApiContext(userPage);
    const listResponse = await userApi.get(secretApi);
    expect(listResponse.ok()).toBeTruthy();
    const listData = await listResponse.json();
    expect(listData.results.map((item: { name: string }) => item.name)).toContain(fixture.secretName);

    const createResponse = await userApi.post(backendApi, {
      data: {
        name: uniqueName('forbidden-backend'),
        backend_type: 'hashicorp',
        api_url: 'http://vault.test:8200',
        secret_engine: 'secret',
        default_namespace: '',
        azure_api_version: '7.5',
        enabled: true,
        description: 'Should be forbidden',
        extra_config: { credentials_key: 'hashicorp-test' },
      },
    });
    expect(createResponse.status()).toBe(403);

    const refreshResponse = await userApi.post(`${secretApi}${fixture.secretId}/refresh/`);
    expect(refreshResponse.status()).toBe(403);
    await context.close();
  } finally {
    removeUserFixture(username);
    await cleanupSecretFixture(adminApi, fixture);
  }
});

test('RBAC object constraints limit visible secrets to the permitted subset', async ({ browser, page }) => {
  const adminApi = await createApiContext(page);
  const allowed = await createSecretFixture(adminApi, 'hashicorp');
  const hidden = await createSecretFixture(adminApi, 'hashicorp');
  await refreshFixture(adminApi, allowed.secretId);
  await refreshFixture(adminApi, hidden.secretId);

  const username = uniqueName('vault-constrained').replace(/[^a-z0-9]/gi, '').toLowerCase();
  const password = 'VaultRbac123!';

  try {
    ensureUserFixture({
      username,
      password,
      permissions: [
        {
          name: `${username}-view-backends`,
          objectTypes: ['netbox_vault.vaultbackend'],
          actions: ['view'],
        },
        {
          name: `${username}-view-secrets`,
          objectTypes: ['netbox_vault.vaultsecret'],
          actions: ['view'],
          constraints: { name: allowed.secretName },
        },
      ],
    });

    const context = await browser.newContext({ storageState: { cookies: [], origins: [] } });
    const userPage = await context.newPage();
    await loginAs(userPage, username, password);
    await userPage.goto(secretListUrl);
    await expect(userPage.getByText(allowed.secretName)).toBeVisible();
    await expect(userPage.getByText(hidden.secretName)).toHaveCount(0);

    const userApi = await createApiContext(userPage);
    const listResponse = await userApi.get(secretApi);
    expect(listResponse.ok()).toBeTruthy();
    const listData = await listResponse.json();
    const names = listData.results.map((item: { name: string }) => item.name);
    expect(names).toContain(allowed.secretName);
    expect(names).not.toContain(hidden.secretName);

    const hiddenDetail = await userApi.get(`${secretApi}${hidden.secretId}/`);
    expect(hiddenDetail.status()).toBe(404);
    await context.close();
  } finally {
    removeUserFixture(username);
    await cleanupSecretFixture(adminApi, allowed);
    await cleanupSecretFixture(adminApi, hidden);
  }
});
