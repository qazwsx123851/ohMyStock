import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: false,
      },
    },
  },
  // E2E (Playwright) runs `vite preview`; mirror the dev proxy so /api reaches
  // the uvicorn backend started by playwright.config.ts webServer. 8001 (not
  // 8000) keeps e2e isolated from a manually started real-DB backend — see
  // web-admin/e2e/constants.ts BACKEND_PORT.
  preview: {
    port: 4173,
    proxy: {
      '/api': {
        target: 'http://localhost:8001',
        changeOrigin: false,
      },
    },
  },
})
