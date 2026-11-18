import process from 'node:process';
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const BACKEND_PORT = process.env.VITE_BACKEND_PORT || 8000
const BACKEND_HTTP = `http://127.0.0.1:${BACKEND_PORT}`
const BACKEND_WS = `ws://127.0.0.1:${BACKEND_PORT}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('three/examples')) return 'three-addons';
          if (id.includes('@react-three')) return 'r3f-vendor';
          if (id.includes('node_modules/three')) return 'three-core';
          if (id.includes('recharts') || id.includes('d3-')) return 'charts-vendor';
          if (id.includes('framer-motion')) return 'motion-vendor';
          if (id.includes('lucide-react')) return 'icons-vendor';
          if (id.includes('react-dom') || id.includes('react-router') || id.includes('scheduler')) {
            return 'react-vendor';
          }
          return undefined;
        },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: BACKEND_HTTP,
        changeOrigin: true,
      },
      '/tts': {
        target: BACKEND_HTTP,
        changeOrigin: true,
      },
      '/ws': {
        target: BACKEND_WS,
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
