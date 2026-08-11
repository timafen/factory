import { existsSync } from "node:fs";
import { createServer } from "node:net";
import { defineConfig, devices } from "@playwright/test";

const defaultBrowserLauncher = "/usr/local/libexec/factory/factory-browser-sandbox";
const e2eHost = "127.0.0.1";
const allocatedE2EPorts = new Set<number>();
export const testWorkerBootstrapCredential =
  process.env.FACTORY_E2E_WORKER_BOOTSTRAP_CREDENTIAL ??
  "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

export function serverBrowserLaunchOptions(
  launcher = process.env.FACTORY_BROWSER_LAUNCHER ?? defaultBrowserLauncher,
) {
  if (!existsSync(launcher)) return undefined;
  return { executablePath: launcher, chromiumSandbox: true };
}

export type E2EServerAddress = {
  port: number;
  backendPort: number;
  origin: string;
  healthURL: string;
};

function parseE2EPort(value: string) {
  if (!/^[0-9]+$/.test(value)) {
    throw new Error(`FACTORY_E2E_PORT must be an integer from 1 to 65535; received ${JSON.stringify(value)}`);
  }
  const port = Number(value);
  if (!Number.isSafeInteger(port) || port < 1 || port > 65_535) {
    throw new Error(`FACTORY_E2E_PORT must be an integer from 1 to 65535; received ${JSON.stringify(value)}`);
  }
  return port;
}

async function findFreeE2EPort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.unref();
    server.once("error", reject);
    server.listen({ host: e2eHost, port: 0, exclusive: true }, () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new Error("Could not allocate a loopback port for the browser fixture"));
        return;
      }
      server.close((error) => {
        if (error) reject(error);
        else resolve(address.port);
      });
    });
  });
}

export async function createE2EServerAddress(
  portOverride?: string,
): Promise<E2EServerAddress> {
  let port = portOverride === undefined ? await findFreeE2EPort() : parseE2EPort(portOverride);
  while (portOverride === undefined && allocatedE2EPorts.has(port)) {
    port = await findFreeE2EPort();
  }
  allocatedE2EPorts.add(port);
  let backendPort = await findFreeE2EPort();
  while (backendPort === port || allocatedE2EPorts.has(backendPort)) {
    backendPort = await findFreeE2EPort();
  }
  allocatedE2EPorts.add(backendPort);
  const backendOrigin = `http://${e2eHost}:${backendPort}`;
  return {
    port,
    backendPort,
    origin: `https://${e2eHost}:${port}`,
    // Playwright's webServer readiness probe cannot validate the fixture's
    // short-lived self-signed certificate. Browsers still use HTTPS above.
    healthURL: `${backendOrigin}/healthz`,
  };
}

export async function createPlaywrightConfig(portOverride?: string) {
  const serverAddress = await createE2EServerAddress(portOverride);
  process.env.FACTORY_E2E_PORT = String(serverAddress.port);
  return defineConfig({
    testDir: "./e2e",
    fullyParallel: false,
    workers: 1,
    timeout: 45_000,
    expect: { timeout: 8_000 },
    reporter: [["list"], ["html", { open: "never" }]],
    outputDir: "test-results/artifacts",
    use: {
      baseURL: serverAddress.origin,
      ignoreHTTPSErrors: true,
      launchOptions: serverBrowserLaunchOptions(),
      trace: "retain-on-failure",
      screenshot: "only-on-failure",
      video: "retain-on-failure",
    },
    projects: [
      {
        name: "chromium",
        use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 1000 } },
      },
    ],
    webServer: {
      command: "node e2e/server.mjs",
      url: serverAddress.healthURL,
      reuseExistingServer: false,
      timeout: 120_000,
      env: {
        FACTORY_E2E_PORT: String(serverAddress.port),
        FACTORY_E2E_BACKEND_PORT: String(serverAddress.backendPort),
        FACTORY_E2E_WORKER_BOOTSTRAP_CREDENTIAL: testWorkerBootstrapCredential,
      },
    },
  });
}

export default await createPlaywrightConfig(process.env.FACTORY_E2E_PORT);
