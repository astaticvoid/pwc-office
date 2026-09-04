// @ts-check
import { defineConfig, devices } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:8080';
const isLocal  = BASE_URL.startsWith('http://localhost');

const AUTH_USER = process.env.AUTH_USER || process.env.BASIC_AUTH_USER;
const AUTH_PASSWORD = process.env.AUTH_PASSWORD || process.env.BASIC_AUTH_PASSWORD;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: isLocal ? 0 : 1,   // one retry on flaky network to Netlify
  reporter: 'list',

  use: {
    baseURL: BASE_URL,
    // Store browser state (cookies, localStorage) per test, not shared.
    storageState: undefined,
    // Basic auth for staging/production if configured in environment (ignored on localhost)
    ...(!isLocal && AUTH_USER && AUTH_PASSWORD && { httpCredentials: { username: AUTH_USER, password: AUTH_PASSWORD } }),
  },

  // When testing locally, start the pre-built dist/ server automatically.
  // Run `make build` first if dist/ is stale.
  // Set reuseExistingServer so `make serve-dist` in another terminal also works.
  webServer: isLocal ? {
    command: 'python3 tools/local_server.py 8080 --directory web',
    port: 8080,
    reuseExistingServer: true,
    timeout: 10_000,
  } : undefined,

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile',   use: { ...devices['Pixel 7'] } },
    { name: 'ios',      use: { ...devices['iPhone 13'] } },
  ],
});
