/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dashboard talks to the read-only FastAPI layer (api/app.py). In development Vite
// proxies /api/* to it, so the browser never needs CORS and the base URL stays relative.
const API_TARGET = process.env.CELERIS_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: true, rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  build: {
    rollupOptions: {
      output: {
        // vendor chunks change rarely and stay cached across releases; ECharts loads with the first chart page
        manualChunks: { echarts: ["echarts", "zrender"], react: ["react", "react-dom", "react-router-dom"] },
      },
    },
    chunkSizeWarningLimit: 800,   // the ECharts chunk (modular import) is ~200 KB gzipped by itself
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
