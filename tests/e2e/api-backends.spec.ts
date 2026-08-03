import { test, expect } from '@playwright/test';
import { createApiContext, uniqueName } from './helpers/netbox.js';
import { getBackendPayload, type BackendKind } from './helpers/backend-fixtures.js';

const apiBase = '/api/plugins/vault/vault-backends/';
const backendTypes: BackendKind[] = [
  'hashicorp',
  'azure_key_vault',
  'google_cloud_secret_manager',
  'aws_secrets_manager',
];

for (const backendType of backendTypes) {
  test(`API CRUD for ${backendType} backends`, async ({ page }) => {
    const api = await createApiContext(page);
    const name = uniqueName(`${backendType}-backend`);

    const createResponse = await api.post(apiBase, {
      data: getBackendPayload(backendType, name),
    });
    expect(createResponse.ok()).toBeTruthy();
    const created = await createResponse.json();

    const listResponse = await api.get(apiBase);
    expect(listResponse.ok()).toBeTruthy();
    const listData = await listResponse.json();
    expect(listData.results.map((item: { name: string }) => item.name)).toContain(name);

    const patchResponse = await api.patch(`${apiBase}${created.id}/`, {
      data: {
        description: `Updated ${backendType} backend`,
        enabled: false,
      },
    });
    expect(patchResponse.ok()).toBeTruthy();
    const updated = await patchResponse.json();
    expect(updated.description).toBe(`Updated ${backendType} backend`);
    expect(updated.enabled).toBe(false);

    const detailResponse = await api.get(`${apiBase}${created.id}/`);
    expect(detailResponse.ok()).toBeTruthy();
    const detail = await detailResponse.json();
    expect(detail.backend_type).toBe(backendType);

    const deleteResponse = await api.delete(`${apiBase}${created.id}/`);
    expect(deleteResponse.status()).toBe(204);
  });
}
