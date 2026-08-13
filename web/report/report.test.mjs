import test from "node:test";
import assert from "node:assert/strict";
import { chmod, readFile, symlink, writeFile, mkdir, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "node:http";
import { once } from "node:events";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { captureVisual } from "./capture.mjs";
import { renderReport } from "./render.mjs";

function restoreEnvironment(name, value) {
  if (value === undefined) delete process.env[name];
  else process.env[name] = value;
}

let installedRuntime;
async function reportBrowserFixture() {
  if (installedRuntime) return installedRuntime;
  const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  execFileSync("npx", ["playwright", "install", "chromium"], { cwd: webRoot, stdio: "inherit" });
  const browser = execFileSync("node", ["-e", "process.stdout.write(require('playwright').chromium.executablePath())"], { cwd: webRoot, encoding: "utf8" }).trim();
  assert.match(browser, /^\//, "Playwright must provide an absolute Chromium executable");
  const root = await mkdtemp(path.join(tmpdir(), "factory-report-runtime-"));
  const runtime = path.join(root, "runtime");
  const launcher = path.join(root, "factory-browser-sandbox");
  await mkdir(runtime);
  await writeFile(path.join(runtime, "package.json"), "{\"private\":true}\n", { mode: 0o600 });
  await symlink(path.join(webRoot, "node_modules"), path.join(runtime, "node_modules"), "dir");
  await writeFile(launcher, `#!/bin/sh\nexec ${JSON.stringify(browser)} "$@"\n`, { mode: 0o700 });
  await chmod(launcher, 0o700);
  installedRuntime = { launcher, runtime };
  return installedRuntime;
}

test("capture requires the isolated launcher, Chromium sandbox, and an allowed host", async () => {
  const source = await readFile(new URL("./capture.mjs", import.meta.url), "utf8");
  const embeddedSource = await readFile(new URL("../../internal/controlplane/report_scripts/capture.mjs", import.meta.url), "utf8");
  assert.match(source, /executablePath:\s*launcher/);
  assert.match(source, /chromiumSandbox:\s*true/);
  assert.match(source, /FACTORY_BROWSER_LAUNCHER/);
  assert.match(source, /allowedHosts\.has\(host\)/);
  assert.match(source, /FACTORY_BROWSER_RUNTIME/);
  assert.match(source, /origin:\s*["']https:\/\/factory\.timafen\.com["']/);
  assert.match(embeddedSource, /origin:\s*["']https:\/\/factory\.timafen\.com["']/);
});

test("capture opens the protected Factory page with Basic Auth only in its context", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-capture-auth-"));
  const runtime = path.join(dir, "runtime");
  const events = path.join(dir, "contexts.jsonl");
  await mkdir(path.join(runtime, "node_modules", "playwright"), { recursive: true });
  await writeFile(path.join(runtime, "package.json"), "{}", "utf8");
  await writeFile(path.join(runtime, "node_modules", "playwright", "index.js"), `
    const fs=require("node:fs");
    exports.chromium={launch:async()=>({newContext:async options=>{fs.appendFileSync(process.env.FACTORY_CAPTURE_EVENTS,JSON.stringify(options)+"\\n");return {newPage:async()=>({goto:async()=>{},url:()=>"https://factory.timafen.com/reports",getByText:()=>({waitFor:async()=>{}}),screenshot:async options=>fs.writeFileSync(options.path,"\\x89PNG\\r\\n\\x1a\\n")}),close:async()=>{}}},close:async()=>{}})};
  `, "utf8");
  const previous = [process.env.FACTORY_BROWSER_BASIC_AUTH_USERNAME, process.env.FACTORY_BROWSER_BASIC_AUTH_PASSWORD, process.env.FACTORY_CAPTURE_EVENTS];
  process.env.FACTORY_BROWSER_BASIC_AUTH_USERNAME = "report-user";
  process.env.FACTORY_BROWSER_BASIC_AUTH_PASSWORD = "report-password";
  process.env.FACTORY_CAPTURE_EVENTS = events;
  try {
    await captureVisual({ url: "https://factory.timafen.com/reports", state_text: "Готово", viewport_width: 800, viewport_height: 600 }, path.join(dir, "factory.png"), "/tmp/factory-launcher", runtime);
    await captureVisual({ url: "https://staging-automation.tarser.net/reports", state_text: "Готово", viewport_width: 800, viewport_height: 600 }, path.join(dir, "staging.png"), "/tmp/factory-launcher", runtime);
  } finally {
    restoreEnvironment("FACTORY_BROWSER_BASIC_AUTH_USERNAME", previous[0]);
    restoreEnvironment("FACTORY_BROWSER_BASIC_AUTH_PASSWORD", previous[1]);
    restoreEnvironment("FACTORY_CAPTURE_EVENTS", previous[2]);
  }
  const contexts = (await readFile(events, "utf8")).trim().split("\n").map(JSON.parse);
  assert.deepEqual(contexts[0].httpCredentials, { username: "report-user", password: "report-password", origin: "https://factory.timafen.com" });
  assert.equal(contexts[1].httpCredentials, undefined);
});

test("capture does not answer a Basic Auth challenge after a redirect to another origin", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-capture-foreign-auth-"));
  const runtime = path.join(dir, "runtime");
  const receivedAuthorization = [];
  const foreignServer = createServer((request, response) => {
    receivedAuthorization.push(request.headers.authorization);
    response.writeHead(401, { "www-authenticate": 'Basic realm="foreign"' });
    response.end("authentication required");
  });
  foreignServer.listen(0, "127.0.0.1");
  await once(foreignServer, "listening");
  const foreignAddress = foreignServer.address();
  const foreignURL = `http://127.0.0.1:${foreignAddress.port}/redirected`;
  await mkdir(path.join(runtime, "node_modules", "playwright"), { recursive: true });
  await writeFile(path.join(runtime, "package.json"), "{}", "utf8");
  await writeFile(path.join(runtime, "node_modules", "playwright", "index.js"), `
    const fs=require("node:fs");
    exports.chromium={launch:async()=>({newContext:async options=>({newPage:async()=>({goto:async()=>{
      const foreignURL=process.env.FACTORY_CAPTURE_REDIRECT_URL;
      const challenged=await fetch(foreignURL);
      const credentials=options.httpCredentials;
      const credentialsApply=credentials && (!credentials.origin || credentials.origin===new URL(foreignURL).origin);
      if(challenged.status===401 && credentialsApply){
        const authorization="Basic "+Buffer.from(credentials.username+":"+credentials.password).toString("base64");
        await fetch(foreignURL,{headers:{authorization}});
      }
    },url:()=>"https://factory.timafen.com/reports",getByText:()=>({waitFor:async()=>{}}),screenshot:async options=>fs.writeFileSync(options.path,"\\x89PNG\\r\\n\\x1a\\n")}),close:async()=>{}}),close:async()=>{}})};
  `, "utf8");
  const previous = {
    username: process.env.FACTORY_BROWSER_BASIC_AUTH_USERNAME,
    password: process.env.FACTORY_BROWSER_BASIC_AUTH_PASSWORD,
    redirectURL: process.env.FACTORY_CAPTURE_REDIRECT_URL,
  };
  process.env.FACTORY_BROWSER_BASIC_AUTH_USERNAME = "factory-user";
  process.env.FACTORY_BROWSER_BASIC_AUTH_PASSWORD = "factory-password";
  process.env.FACTORY_CAPTURE_REDIRECT_URL = foreignURL;
  try {
    await captureVisual({ url: "https://factory.timafen.com/reports", state_text: "Готово", viewport_width: 800, viewport_height: 600 }, path.join(dir, "factory.png"), "/tmp/factory-launcher", runtime);
  } finally {
    restoreEnvironment("FACTORY_BROWSER_BASIC_AUTH_USERNAME", previous.username);
    restoreEnvironment("FACTORY_BROWSER_BASIC_AUTH_PASSWORD", previous.password);
    restoreEnvironment("FACTORY_CAPTURE_REDIRECT_URL", previous.redirectURL);
    foreignServer.close();
    await once(foreignServer, "close");
  }
  assert.deepEqual(receivedAuthorization, [undefined]);
});

test("renderer uses the same installed launcher, sandbox, and runtime", async () => {
  const source = await readFile(new URL("./render.mjs", import.meta.url), "utf8");
  assert.match(source, /executablePath:\s*launcher/);
  assert.match(source, /chromiumSandbox:\s*true/);
  assert.match(source, /FACTORY_BROWSER_RUNTIME/);
  assert.match(source, /route\("\*\*\/\*"/);
});

test("renderer produces a PDF with an inline screenshot without fetching external resources", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "factory-report-"));
  const output = path.join(dir, "daily.pdf");
  const { launcher, runtime } = await reportBrowserFixture();
  await renderReport("<h1>Ежедневный отчёт</h1><img alt='Снимок до' src='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M/wHwAF/gL+V9ZqAAAAAElFTkSuQmCC'><img src='https://invalid.example/nope.png'>", output, launcher, runtime);
  const bytes = await readFile(output);
  assert.equal(bytes.subarray(0, 5).toString(), "%PDF-");
});

test("capture uses the installed Chromium runtime for a late after screenshot", async () => {
  const { launcher, runtime } = await reportBrowserFixture();
  const server = createServer((_request, response) => {
    response.setHeader("content-type", "text/html; charset=utf-8");
    response.end("<!doctype html><title>Factory</title><main>После готово</main>");
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  try {
    const address = server.address();
    const output = path.join(await mkdtemp(path.join(tmpdir(), "factory-capture-")), "after.png");
    await captureVisual({
      url: `http://127.0.0.1:${address.port}/reports`,
      state_text: "После готово",
      viewport_width: 800,
      viewport_height: 600,
    }, output, launcher, runtime);
    const bytes = await readFile(output);
    assert.equal(bytes.subarray(1, 4).toString(), "PNG");
  } finally {
    server.close();
    await once(server, "close");
  }
});
