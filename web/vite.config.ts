import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
    exclude: ["e2e/**", "node_modules/**"],
    // The release gate runs next to active Factory workers. Keep the suite
    // bounded so CPU contention does not turn healthy tests into 5s timeouts.
    maxWorkers: 4,
    testTimeout: 15_000,
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:7337",
      "/healthz": "http://127.0.0.1:7337",
    },
  },
});
