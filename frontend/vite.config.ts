import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'
import { defineConfig } from 'vite'

// The dev server proxies /chat to FastAPI so the browser only ever talks to
// one origin. Same-origin means no CORS on the API, no preflight, and nothing
// to get wrong later when the conversation id arrives. Sage stays a plain
// JSON service that curl can still drive.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Covers /chat and /chat/stream.
      '/chat': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
