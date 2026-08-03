import { APIRequestContext, expect } from '@playwright/test';
import { putAwsSecret, putAzureSecret, putGoogleSecret, putHashicorpSecret } from './vault.js';
import { uniqueName } from './netbox.js';

export type BackendKind = 'hashicorp' | 'azure_key_vault' | 'google_cloud_secret_manager' | 'aws_secrets_manager';

export type SecretFixture = {
  backendId: number;
  backendName: string;
  backendPayload: Record<string, unknown>;
  externalSecretName: string;
  plainValue: string;
  secretId: number;
  secretName: string;
};

const backendApi = '/api/plugins/vault/vault-backends/';
const secretApi = '/api/plugins/vault/vault-secrets/';

export async function createSecretFixture(api: APIRequestContext, backendType: BackendKind): Promise<SecretFixture> {
  const backendName = uniqueName(`${backendType}-backend`);
  const secretName = uniqueName(`${backendType}-secret`);
  const externalSecretName = `${backendType}-source-${Date.now()}`;
  const plainValue = `${backendType}-value-${Date.now()}`;

  const backendPayload = getBackendPayload(backendType, backendName);
  const backendResponse = await api.post(backendApi, { data: backendPayload });
  expect(backendResponse.ok()).toBeTruthy();
  const backend = await backendResponse.json();

  await seedBackendSecret(backendType, externalSecretName, plainValue);

  const secretResponse = await api.post(secretApi, {
    data: {
      name: secretName,
      vault_backend_id: backend.id,
      secret_path: externalSecretName,
      secret_key: 'value',
      refresh_interval_hours: 1,
      enabled: true,
      description: `${backendType} fixture secret`,
    },
  });
  expect(secretResponse.ok()).toBeTruthy();
  const secret = await secretResponse.json();

  return {
    backendId: backend.id,
    backendName,
    backendPayload,
    externalSecretName,
    plainValue,
    secretId: secret.id,
    secretName,
  };
}

export async function refreshFixture(api: APIRequestContext, secretId: number) {
  const response = await api.post(`${secretApi}${secretId}/refresh/`);
  expect(response.ok()).toBeTruthy();
  return response.json();
}

export async function cleanupSecretFixture(api: APIRequestContext, fixture: SecretFixture) {
  await api.delete(`${secretApi}${fixture.secretId}/`);
  await api.delete(`${backendApi}${fixture.backendId}/`);
}

export function getBackendPayload(backendType: BackendKind, backendName: string) {
  const common = {
    name: backendName,
    secret_engine: '',
    default_namespace: '',
    azure_api_version: '7.5',
    enabled: true,
    description: `${backendType} backend fixture`,
  };

  switch (backendType) {
    case 'hashicorp':
      return {
        ...common,
        backend_type: 'hashicorp',
        api_url: 'http://vault.test:8200',
        secret_engine: 'secret',
        extra_config: { credentials_key: 'hashicorp-test' },
      };
    case 'azure_key_vault':
      return {
        ...common,
        backend_type: 'azure_key_vault',
        api_url: 'https://azure-keyvault.test:4997',
        extra_config: { verify_tls: false, credentials_key: 'azure-test' },
      };
    case 'google_cloud_secret_manager':
      return {
        ...common,
        backend_type: 'google_cloud_secret_manager',
        api_url: 'http://gcp-secret-manager.test:8080',
        extra_config: { credentials_key: 'gcp-test' },
      };
    case 'aws_secrets_manager':
      return {
        ...common,
        backend_type: 'aws_secrets_manager',
        api_url: 'http://aws-secrets.test:5000',
        extra_config: { credentials_key: 'aws-test' },
      };
  }
}

async function seedBackendSecret(backendType: BackendKind, externalSecretName: string, plainValue: string) {
  switch (backendType) {
    case 'hashicorp':
      await putHashicorpSecret(externalSecretName, 'value', plainValue);
      return;
    case 'azure_key_vault':
      await putAzureSecret(externalSecretName, plainValue);
      return;
    case 'google_cloud_secret_manager':
      await putGoogleSecret(externalSecretName, plainValue);
      return;
    case 'aws_secrets_manager':
      await putAwsSecret(externalSecretName, plainValue);
      return;
  }
}
