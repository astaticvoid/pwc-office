// @ts-check
const { defineConfig, devices } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'https://taupe-lokum-ec81da.netlify.app';
const isLocal  = BASE_URL.startsWith('http://localhost');

module.exports = defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  retries: isLocal ? 0 : 1,   // one retry on flaky network to Netlify
  reporter: 'list',

  use: {
    baseURL: BASE_URL,
    // Store browser state (cookies, localStorage) per test, not shared.
    storageState: undefined,
  },

  // When testing locally, start the pre-built dist/ server automatically.
  // Run `make build` first if dist/ is stale.
  // Set reuseExistingServer so `make serve-dist` in another terminal also works.
  webServer: isLocal ? {
    command: 'python3 -m http.server 8081 --directory dist',
    url: BASE_URL,
    reuseExistingServer: true,
    timeout: 10_000,
  } : undefined,

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'mobile',   use: { ...devices['Pixel 7'] } },
  ],
});
