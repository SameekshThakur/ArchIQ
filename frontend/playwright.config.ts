import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, devices } from '@playwright/test';

/*
 * End-to-end tests run the production build against a real API, as a user would meet them.
 *
 *   npm run e2e            builds, starts both servers, runs the suite
 *   npm run e2e:ui         the same with Playwright's interactive runner
 *
 * One-off setup:  npx playwright install chromium
 * Already have Chrome and no downloads?  set PW_CHROMIUM_PATH to its executable.
 * The API and preview server run on their own ports (8100 and 4273) with a throw-away database, so the suite never touches
 * a development copy. E2E_REUSE=1 reuses servers already running there, for quick re-runs.
 */
const here = fileURLToPath(new URL('.', import.meta.url));
const backend = resolve(here, '../backend');
const venvPython = [join(backend, '.venv', 'Scripts', 'python.exe'), join(backend, '.venv', 'bin', 'python')].find(existsSync);
const python = process.env.E2E_PYTHON ?? venvPython ?? (process.platform === 'win32' ? 'python' : 'python3');
const WEB = 4273;
// its own ports and database, so a running development copy is never touched (the specs delete what they create)
const API = 8100;

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 10_000 },
  // the specs share one API and its database, so they run one at a time
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : [['list']],
  use: {
    baseURL: `http://127.0.0.1:${WEB}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1440, height: 900 },
    ...(process.env.PW_CHROMIUM_PATH ? { launchOptions: { executablePath: process.env.PW_CHROMIUM_PATH } } : {}),
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } }],
  webServer: [
    {
      command: `"${python}" -m uvicorn app.main:app --host 127.0.0.1 --port ${API}`,
      cwd: backend,
      url: `http://127.0.0.1:${API}/api/v1/graph/views`,
      env: { ARCHIQ_DB: join(tmpdir(), `archiq-e2e-${process.pid}.db`), PYTHONUTF8: '1' },
      reuseExistingServer: !!process.env.E2E_REUSE,
      timeout: 90_000,
    },
    {
      command: `npx vite preview --host 127.0.0.1 --port ${WEB} --strictPort`,
      url: `http://127.0.0.1:${WEB}`,
      env: { ARCHIQ_API_URL: `http://127.0.0.1:${API}` },
      reuseExistingServer: !!process.env.E2E_REUSE,
      timeout: 60_000,
    },
  ],
});
