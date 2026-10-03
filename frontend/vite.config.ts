import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API is proxied so no backend URL or secret is baked into the bundle.
const proxy = {
  "/api": { target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000", changeOrigin: true },
};
// Allow public tunnel hostnames (ngrok) in addition to localhost.
const allowedHosts = [".ngrok-free.app", ".ngrok.app", ".ngrok-free.dev", ".ngrok.dev"];

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy, allowedHosts },
  preview: { port: 4173, proxy, allowedHosts },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1200 },
});
