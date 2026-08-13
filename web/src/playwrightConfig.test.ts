import { createHash, X509Certificate } from "node:crypto";
import { closeSync, mkdtempSync, openSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import {
  coldHTTPSFixtureSetupTimeout,
  configureColdHTTPSFixtureSetupTimeout,
  createE2EServerAddress,
  createPlaywrightConfig,
  httpsFixtureCertificate,
  serverBrowserLaunchOptions,
  testWorkerBootstrapCredential,
} from "../playwright.config";

const temporaryDirectories: string[] = [];

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true });
  }
});

describe("server browser launcher", () => {
  it("provides a valid isolated worker bootstrap credential to the browser fixture", () => {
    expect(testWorkerBootstrapCredential).toMatch(/^[A-Za-z0-9_-]{43}$/);
  });

  it("uses an installed launcher and keeps the Chromium sandbox enabled", () => {
    const directory = mkdtempSync(join(tmpdir(), "factory-browser-launcher-"));
    temporaryDirectories.push(directory);
    const launcher = join(directory, "factory-browser-sandbox");
    closeSync(openSync(launcher, "w"));

    expect(serverBrowserLaunchOptions(launcher)).toEqual({
      args: [
        `--ignore-certificate-errors-spki-list=${httpsFixtureCertificate.spkiSHA256}`,
      ],
      executablePath: launcher,
      chromiumSandbox: true,
    });
  });

  it("trusts only the HTTPS fixture certificate with the default Chromium", () => {
    const certificate = new X509Certificate(
      readFileSync(httpsFixtureCertificate.certificatePath),
    );
    expect(certificate.checkIP("127.0.0.1")).toBe("127.0.0.1");
    expect(
      createHash("sha256")
        .update(certificate.publicKey.export({ type: "spki", format: "der" }))
        .digest("base64"),
    ).toBe(httpsFixtureCertificate.spkiSHA256);
    expect(process.env.FACTORY_E2E_TLS_KEY).toBe(httpsFixtureCertificate.keyPath);
    expect(process.env.FACTORY_E2E_TLS_CERTIFICATE).toBe(
      httpsFixtureCertificate.certificatePath,
    );
    expect(serverBrowserLaunchOptions("/missing/factory-browser-sandbox")).toEqual({
      args: [
        `--ignore-certificate-errors-spki-list=${httpsFixtureCertificate.spkiSHA256}`,
      ],
    });
    expect(serverBrowserLaunchOptions("/missing/factory-browser-sandbox").args).not.toContain(
      "--ignore-certificate-errors",
    );
  });
});

describe("browser fixture server address", () => {
  it("bounds cold HTTPS fixture setup with an explicit finite timeout", () => {
    const appliedTimeouts: number[] = [];

    configureColdHTTPSFixtureSetupTimeout((timeout) => appliedTimeouts.push(timeout));

    expect(appliedTimeouts).toEqual([120_000]);
    expect(Number.isFinite(coldHTTPSFixtureSetupTimeout)).toBe(true);
    expect(coldHTTPSFixtureSetupTimeout).toBeGreaterThan(31_000);
  });

  it("uses an explicit valid port for every Playwright consumer", async () => {
    const config = await createPlaywrightConfig("24567");
    const reloadedConfig = await createPlaywrightConfig(process.env.FACTORY_E2E_PORT);

    expect(config.use?.baseURL).toBe("https://127.0.0.1:24567");
    expect(reloadedConfig.use?.baseURL).toBe(config.use?.baseURL);
    expect(config.use?.ignoreHTTPSErrors).toBeUndefined();
    const webServer = Array.isArray(config.webServer) ? config.webServer[0] : config.webServer;
    expect(webServer).toMatchObject({
      command: "node e2e/server.mjs",
      env: {
        FACTORY_E2E_PORT: "24567",
        FACTORY_E2E_TLS_KEY: httpsFixtureCertificate.keyPath,
        FACTORY_E2E_TLS_CERTIFICATE: httpsFixtureCertificate.certificatePath,
      },
    });
    const backendPort = webServer?.env?.FACTORY_E2E_BACKEND_PORT;
    expect(backendPort).toMatch(/^[0-9]+$/);
    expect(webServer?.url).toBe(`http://127.0.0.1:${backendPort}/healthz`);
  });

  it("keeps intercepted HTTPS requests in Chromium and captures sanitized proxy headers", () => {
    const specification = readFileSync(
      join(process.cwd(), "e2e/control-plane.spec.ts"),
      "utf8",
    );
    const fixtureServer = readFileSync(join(process.cwd(), "e2e/server.mjs"), "utf8");

    expect(specification).not.toContain("route.fetch(");
    expect(specification).toMatch(
      /test\("shows project readiness card"[\s\S]*?page\.evaluate\(async \(\) => \{[\s\S]*?fetch\("\/api\/v1\/dashboard"\)[\s\S]*?page\.reload\(\)/,
    );
    expect(specification).toMatch(
      /test\("shows project readiness card"[\s\S]*?navigator\.serviceWorker\.ready[\s\S]*?registration\.active\?\.scriptURL[\s\S]*?expect\(activeServiceWorker\)\.toMatch\(\/\\\/sw\\\.js\$\//,
    );
    expect(specification).toContain("route.continue({");
    expect(specification).toContain('"x-factory-e2e-backend-forwarded-host"');
    expect(fixtureServer).toContain('responseHeaders["x-factory-e2e-client-origin"]');
    expect(fixtureServer).toContain('responseHeaders["x-factory-e2e-backend-forwarded-host"]');
    expect(fixtureServer).not.toContain("NODE_TLS_REJECT_UNAUTHORIZED");
  });

  it.each(["", "0", "65536", "12.5", "not-a-port"]) (
    "rejects invalid FACTORY_E2E_PORT value %j",
    async (value) => {
      await expect(createE2EServerAddress(value)).rejects.toThrow(
        "FACTORY_E2E_PORT must be an integer from 1 to 65535",
      );
    },
  );

  it("allocates distinct usable loopback ports for independent runs", async () => {
    const [first, second] = await Promise.all([
      createE2EServerAddress(),
      createE2EServerAddress(),
    ]);

    expect(first.port).toBeGreaterThan(0);
    expect(first.port).toBeLessThanOrEqual(65_535);
    expect(second.port).not.toBe(first.port);
    expect(first.backendPort).not.toBe(first.port);
    expect(second.backendPort).not.toBe(second.port);
    expect(first.origin).toBe(`https://127.0.0.1:${first.port}`);
    expect(second.origin).toBe(`https://127.0.0.1:${second.port}`);
  });
});
