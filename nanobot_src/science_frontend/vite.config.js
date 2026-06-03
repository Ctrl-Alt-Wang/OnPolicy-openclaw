import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api/model': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/api/hermes': {
        target: 'http://localhost:18080',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/hermes/, ''),
      },
    },
  },
})
