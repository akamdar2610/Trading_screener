import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // In dev, `npm run dev` serves the frontend on its own port; this proxies
    // /api calls to the FastAPI server so App.jsx's relative fetch("/api/...")
    // works without any config changes between dev and production.
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
