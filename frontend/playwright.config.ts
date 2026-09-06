import { defineConfig, devices } from '@playwright/test'

/**
 * Minimal browser coverage for the research task critical path
 * (create → land on /research/:id → refresh → recover). See e2e/README.md.
 *
 * Both servers are started by Playwright. The backend runs the deterministic
 * Mock runtime against a throwaway SQLite database (backend/scripts/serve_e2e.py);
 * the frontend runs the Vite dev server so the browser only ever talks to one
 * origin and the `/api` proxy forwards to the backend.
 */
const CI = Boolean(process.env.CI)
const API_PORT = process.env.QUNXUE_E2E_PORT ?? '8000'
const WEB_PORT = process.env.QUNXUE_E2E_WEB_PORT ?? '5173'
const API_ORIGIN = `http://127.0.0.1:${API_PORT}`
const WEB_ORIGIN = `http://127.0.0.1:${WEB_PORT}`

export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  fullyParallel: false,
  workers: 1,
  forbidOnly: CI,
  retries: CI ? 1 : 0,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: CI
    ? [['list'], ['html', { open: 'never' }]]
    : [['list']],
  globalSetup: './e2e/global-setup.ts',
  use: {
    baseURL: WEB_ORIGIN,
    storageState: './e2e/.artifacts/storage-state.json',
    trace: 'on-first-retry',
    video: 'off',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: [
    {
      command: 'uv run --cache-dir .cache/uv python scripts/serve_e2e.py',
      cwd: '../backend',
      url: `${API_ORIGIN}/api/health`,
      reuseExistingServer: !CI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 240_000,
      // serve_e2e.py recreates backend/var/e2e.db from an empty schema on start.
      env: { QUNXUE_E2E_PORT: API_PORT },
    },
    {
      // Bind IPv4 explicitly: Vite's default `localhost` can resolve to ::1 only,
      // which Playwright's 127.0.0.1 readiness probe never reaches.
      command: `npm run dev -- --host 127.0.0.1 --port ${WEB_PORT} --strictPort`,
      cwd: '.',
      url: WEB_ORIGIN,
      reuseExistingServer: !CI,
      stdout: 'pipe',
      stderr: 'pipe',
      timeout: 240_000,
      env: { VITE_API_PROXY_TARGET: API_ORIGIN },
    },
  ],
})
