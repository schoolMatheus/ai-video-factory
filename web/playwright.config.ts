import { defineConfig, devices } from "@playwright/test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const python = resolve(
  root,
  process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
);

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8766",
    trace: "retain-on-failure",
    ...devices["Desktop Chrome"],
  },
  webServer: {
    command: `"${python}" "${resolve(root, "scripts/e2e_serve.py")}"`,
    url: "http://127.0.0.1:8766/__e2e/ping",
    reuseExistingServer: true,
    timeout: 30_000,
  },
});
