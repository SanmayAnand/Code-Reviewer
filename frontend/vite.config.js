import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run build` writes straight into the backend so FastAPI serves the UI on one port.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../backend/app/static", emptyOutDir: true },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8000" } },
});
