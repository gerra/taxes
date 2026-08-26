import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// Dev: Vite serves the SPA on :5173 and proxies API + OAuth to Flask on :5002.
const proxyTargets = ['/api', '/oauth', '/logout']

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(proxyTargets.map((p) => [p, 'http://localhost:5002'])),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
  },
})
