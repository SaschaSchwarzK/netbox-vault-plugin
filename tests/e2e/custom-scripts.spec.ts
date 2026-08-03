import { test, expect } from '@playwright/test';
import { cleanupSecretFixture, createSecretFixture, refreshFixture, type BackendKind } from './helpers/backend-fixtures.js';
import { createApiContext, getPlainValueThroughService } from './helpers/netbox.js';
import { runNetboxScript } from './helpers/docker.js';

const backendTypes: BackendKind[] = [
  'hashicorp',
  'azure_key_vault',
  'google_cloud_secret_manager',
  'aws_secrets_manager',
];

for (const backendType of backendTypes) {
  test(`custom script can read cached secret from ${backendType}`, async ({ page }) => {
    const api = await createApiContext(page);
    const fixture = await createSecretFixture(api, backendType);
    await refreshFixture(api, fixture.secretId);
    expect(getPlainValueThroughService(fixture.secretName)).toContain(fixture.plainValue);

    const moduleName = `plugin_secret_${backendType}_${Date.now()}`.replace(/[^a-z0-9_]/g, '_');
    const scriptName = 'ReadSecretValue';
    const script = `from extras.scripts import Script
from netbox_vault.secrets import get_secret_value


class ${scriptName}(Script):
    class Meta:
        name = ${JSON.stringify(`Read cached secret for ${backendType}`)}

    def run(self, data, commit):
        value = get_secret_value(${JSON.stringify(fixture.secretName)})
        self.log_success(f"PLUGIN_SECRET::{value}")
`;

    const uploadResponse = await api.post('/api/extras/scripts/upload/', {
      multipart: {
        file: {
          name: `${moduleName}.py`,
          mimeType: 'text/x-python',
          buffer: Buffer.from(script, 'utf8'),
        },
      },
    });
    expect(uploadResponse.ok()).toBeTruthy();

    try {
      const result = runNetboxScript(`${moduleName}.${scriptName}`, 'admin');
      const messages = (result.jobData?.log ?? []).map((entry: { message?: string }) => entry.message ?? '');
      expect(messages).toContain(`PLUGIN_SECRET::${fixture.plainValue}`);
    } finally {
      await cleanupSecretFixture(api, fixture);
    }
  });
}
