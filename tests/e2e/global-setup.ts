import { expect, request } from '@playwright/test';
import fs from 'node:fs/promises';
import path from 'node:path';
import { adminPassword, adminUser, netboxBaseUrl } from './helpers/config.js';

export default async function globalSetup() {
  const authDir = path.resolve('tests/e2e/.auth');
  await fs.mkdir(authDir, { recursive: true });

  const context = await request.newContext({
    baseURL: netboxBaseUrl,
    extraHTTPHeaders: {
      Referer: `${netboxBaseUrl}/login/`,
    },
  });

  const loginPage = await context.get('/login/');
  expect(loginPage.ok()).toBeTruthy();

  const stateAfterGet = await context.storageState();
  const csrfCookie = stateAfterGet.cookies.find((cookie) => cookie.name === 'csrftoken');
  if (!csrfCookie) {
    throw new Error('Missing csrftoken cookie from login page response');
  }

  const loginResponse = await context.post('/login/', {
    form: {
      csrfmiddlewaretoken: csrfCookie.value,
      next: '/',
      username: adminUser,
      password: adminPassword,
    },
  });

  expect(loginResponse.status()).toBeLessThan(400);
  await context.storageState({ path: path.join(authDir, 'user.json') });
  await context.dispose();
}
