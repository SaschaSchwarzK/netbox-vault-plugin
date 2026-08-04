import { execFileSync } from 'node:child_process';
import { expect } from '@playwright/test';
import { awsRegion, azureAccessToken, azureBaseUrl, gcpBaseUrl, gcpProjectId, hashicorpBaseUrl } from './config.js';
import { netboxPython } from './docker.js';

function runCurl(args: string[]) {
  return execFileSync('curl', args, {
    encoding: 'utf-8',
    stdio: ['pipe', 'pipe', 'pipe'],
  });
}

export async function putHashicorpSecret(secretPath: string, key: string, value: string) {
  runCurl([
    '-sSf',
    '-X',
    'POST',
    `${hashicorpBaseUrl}/v1/secret/data/${secretPath}`,
    '-H',
    `X-Vault-Token: ${process.env.VAULT_TEST_ROOT_TOKEN ?? 'root'}`,
    '-H',
    'Content-Type: application/json',
    '-d',
    JSON.stringify({ data: { [key]: value } }),
  ]);

  const verify = runCurl([
    '-sSf',
    `${hashicorpBaseUrl}/v1/secret/data/${secretPath}`,
    '-H',
    `X-Vault-Token: ${process.env.VAULT_TEST_ROOT_TOKEN ?? 'root'}`,
  ]);
  expect(verify).toContain(secretPath);
  expect(verify).toContain(key);
  expect(verify).toContain(value);
}

export async function putAzureSecret(secretName: string, value: string) {
  runCurl([
    '-sSf',
    '-k',
    '-X',
    'PUT',
    `${azureBaseUrl}/secrets/${secretName}?api-version=7.5`,
    '-H',
    `Authorization: Bearer ${azureAccessToken}`,
    '-H',
    'Content-Type: application/json',
    '-d',
    JSON.stringify({ value }),
  ]);

  const verify = runCurl([
    '-sSf',
    '-k',
    `${azureBaseUrl}/secrets/${secretName}?api-version=7.5`,
    '-H',
    `Authorization: Bearer ${azureAccessToken}`,
  ]);
  expect(verify).toContain(secretName);
  expect(verify).toContain(value);
}

export async function putGoogleSecret(secretName: string, value: string) {
  const secretResource = `projects/${gcpProjectId}/secrets/${secretName}`;
  try {
    runCurl([
      '-sSf',
      '-X',
      'POST',
      `${gcpBaseUrl}/v1/projects/${gcpProjectId}/secrets?secretId=${encodeURIComponent(secretName)}`,
      '-H',
      'Content-Type: application/json',
      '-d',
      JSON.stringify({ replication: { automatic: {} } }),
    ]);
  } catch (error) {
    const message = String(error);
    if (!message.includes('409')) {
      throw error;
    }
  }

  runCurl([
    '-sSf',
    '-X',
    'POST',
    `${gcpBaseUrl}/v1/${secretResource}:addVersion`,
    '-H',
    'Content-Type: application/json',
    '-d',
    JSON.stringify({ payload: { data: Buffer.from(value, 'utf8').toString('base64') } }),
  ]);

  const verify = runCurl([
    '-sSf',
    `${gcpBaseUrl}/v1/${secretResource}/versions/latest:access`,
  ]);
  expect(verify).toContain(secretName);
  expect(verify).toContain(Buffer.from(value, 'utf8').toString('base64'));
}

export async function putAwsSecret(secretName: string, value: string) {
  const script = [
    'import boto3',
    `client = boto3.client('secretsmanager', region_name=${JSON.stringify(awsRegion)}, endpoint_url='http://aws-secrets.test:5000', aws_access_key_id='test', aws_secret_access_key='test')`,
    'try:',
    `    client.create_secret(Name=${JSON.stringify(secretName)}, SecretString=${JSON.stringify(value)})`,
    'except client.exceptions.ResourceExistsException:',
    '    pass',
    `client.put_secret_value(SecretId=${JSON.stringify(secretName)}, SecretString=${JSON.stringify(value)})`,
    `response = client.get_secret_value(SecretId=${JSON.stringify(secretName)})`,
    "print(response['Name'])",
    "print(response['SecretString'])",
  ].join('\n');
  const result = netboxPython(script);
  expect(result).toContain(secretName);
  expect(result).toContain(value);
}
