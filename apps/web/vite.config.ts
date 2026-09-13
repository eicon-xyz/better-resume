import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const API_TARGET = process.env.BR_WEB_API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Same-origin shape in development: the SPA calls /api/v1/... and the dev server proxies it.
    proxy: {
      // ws: true lets /api/v1/media/transcribe upgrade through the dev server.
      "/api": { target: API_TARGET, changeOrigin: true, ws: true },
      "/healthz": { target: API_TARGET, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
