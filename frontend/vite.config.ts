import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build lands in the Python package so `constellation open` serves it; `npm run dev` proxies the API to a running server.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "./", // relative asset paths, so the same build also runs as a static Snapshot site
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  build: { outDir: "../src/constellation/static", emptyOutDir: true, chunkSizeWarningLimit: 800 },
  server: { proxy: { "/api": `http://127.0.0.1:${process.env.CONSTELLATION_PORT ?? 8765}` } },
});
