import path from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Build straight into the Python package: `agent_notify.main` serves
// static/index.html and static/assets/* — no server changes needed per build.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
  build: {
    outDir: path.resolve(__dirname, "../agent_notify/static"),
    emptyOutDir: true,
  },
})
