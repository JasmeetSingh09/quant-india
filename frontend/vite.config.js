import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/api/, ''),
      },
    },
  },

  build: {
    sourcemap: false,          // no source maps in production (smaller deploy)
    chunkSizeWarningLimit: 800,
    rollupOptions: {
      output: {
        // Split large vendor libs into their own chunks so the browser can
        // cache them independently of your app code.
        manualChunks: {
          'react-vendor':    ['react', 'react-dom', 'react-router-dom'],
          'query-vendor':    ['@tanstack/react-query'],
          'charts-vendor':   ['recharts'],
          'icons-vendor':    ['lucide-react'],
          'http-vendor':     ['axios'],
        },
      },
    },
  },
})
