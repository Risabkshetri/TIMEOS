import { defineConfig, devices } from "@playwright/test";

// §25: "E2E smoke". Runs against a dev server this config starts itself, against whatever
// backend BACKEND_INTERNAL_URL / DASHBOARD_PASSWORD point at (see e2e/auth.setup.ts) — a real
// Postgres-backed API, not a mock, matching this project's stated preference for testing against
// real infrastructure over stubs.
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: true,
    timeout: 30_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
