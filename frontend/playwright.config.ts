import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright E2E Test Configuration
 * Frontend: React 18 + Vite on http://localhost:3000
 * Backend API: http://localhost:8000
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },

  // 0 retries locally, 2 in CI
  retries: process.env.CI ? 2 : 0,

  // Parallel workers: 1 in CI for stability, auto locally
  workers: process.env.CI ? 1 : undefined,

  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report', open: 'never' }],
  ],

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'off',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Automatically start Vite dev server before running tests
  webServer: {
    command: 'yarn dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
});
