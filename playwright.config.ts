import { defineConfig } from '@playwright/test';

const baseURL = process.env.NETBOX_BASE_URL ?? `http://127.0.0.1:${process.env.NETBOX_TEST_PORT ?? '8001'}`;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  fullyParallel: false,
  retries: 0,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],
  globalSetup: './tests/e2e/global-setup.ts',
  use: {
    baseURL,
    channel: 'chromium',
    headless: process.env.PLAYWRIGHT_HEADLESS !== '0',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    storageState: './tests/e2e/.auth/user.json',
  },
});
