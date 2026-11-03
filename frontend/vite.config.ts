import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Forward API calls to the local FastAPI backend. The browser only ever
    // talks to this dev server, so no provider keys or CORS setup reach it.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
