import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Dev: API-calls doorsturen naar de lokale backend (uvicorn --reload)
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
