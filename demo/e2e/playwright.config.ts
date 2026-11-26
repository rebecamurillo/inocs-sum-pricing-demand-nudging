import { defineConfig, devices } from '@playwright/test';

// No webServer: `make e2e` starts the stack (compose.e2e.yaml) and removes it afterwards.
// The fakes' state is the one `fake_settings` row the worker's fakes read, so scenarios run
// one at a time.
export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report' }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:14400',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
});
