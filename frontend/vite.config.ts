import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const trialApiProxyTarget =
  (globalThis as { process?: { env?: Record<string, string | undefined> } }).process?.env
    ?.VITE_TRIAL_API_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api/v1/trial": {
        target: trialApiProxyTarget,
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    globals: true,
    include: ["src/test/**/*.test.{ts,tsx}"],
  },
});
