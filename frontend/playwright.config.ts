import { defineConfig, devices } from '@playwright/test';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const projectRoot = path.resolve(__dirname, '..');

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['line'],
  ],
  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServers: process.env.CI ? [
    {
      command: 'node frontend/scripts/start-backend.mjs',
      cwd: projectRoot,
      port: 8000,
      timeout: 120_000,
    },
    {
      command: 'npx vite --port 5173 --host 127.0.0.1',
      cwd: path.join(projectRoot, 'frontend'),
      port: 5173,
      timeout: 120_000,
    },
  ] : undefined,
});