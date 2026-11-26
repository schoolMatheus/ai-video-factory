import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const webRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const localPython = resolve(
  webRoot,
  "..",
  process.platform === "win32" ? ".venv/Scripts/python.exe" : ".venv/bin/python",
);
const python = process.env.PYTHON || (existsSync(localPython) ? localPython : "python");

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: webRoot,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) process.exit(result.status ?? 1);
}

run(python, [resolve(webRoot, "..", "scripts", "dump_openapi.py")]);
run("npx", [
  "openapi-typescript",
  resolve(webRoot, "openapi.json"),
  "-o",
  resolve(webRoot, "src", "api", "generated.ts"),
]);
