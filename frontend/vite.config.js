import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The API target is configuration, never a hardcoded URL.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_PORT) || 5173,
      proxy: {
        '/api': { target, changeOrigin: true },
      },
    },
  }
})
