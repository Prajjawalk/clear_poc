import { defineConfig } from 'vite'
import { resolve } from 'path'

export default defineConfig({
  root: './frontend',
  base: '/static/dist/',
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    manifest: 'manifest.json',
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'frontend/js/main.js'),
        dataMap: resolve(__dirname, 'frontend/js/dataMap.js'),
      },
      output: {
        // Manual chunk splitting for better caching
        manualChunks: {
          'vendor-leaflet': ['leaflet', 'leaflet.markercluster'],
          'vendor-bootstrap': ['bootstrap']
        }
      },
      external: [
        // Suppress warnings for Django-served static assets
        // These are resolved at runtime by Django's static files system
        /^\/static\/fonts\/.*/,
        /^\/static\/dist\/leaflet\/.*/
      ]
    },
    // Only generate sourcemaps in development
    sourcemap: process.env.NODE_ENV !== 'production'
  },
  server: {
    port: 3000,
    host: true,  // Listen on all addresses
    cors: true,  // Enable CORS for Django integration
    fs: {
      // Allow serving files from project root and node_modules
      allow: [resolve(__dirname, '.'), resolve(__dirname, 'node_modules')]
    },
    proxy: {
      // Proxy Django dev server for seamless development
      '/api': 'http://localhost:8000',
      '/admin': 'http://localhost:8000',
      '/healthcheck': 'http://localhost:8000'
    }
  },
  // CSS handling
  css: {
    preprocessorOptions: {
      scss: {
        api: 'modern-compiler',
        quietDeps: true
      }
    }
  },

  // Plugins
  plugins: [],

  // Resolve aliases
  resolve: {
    alias: {
      '@': resolve(__dirname, 'frontend'),
      'bootstrap': resolve(__dirname, 'node_modules/bootstrap'),
      'bootstrap-icons': resolve(__dirname, 'node_modules/bootstrap-icons'),
      'leaflet': resolve(__dirname, 'node_modules/leaflet')
    }
  },

  // Vitest configuration
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './frontend/js/__tests__/setup.js',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/**',
        'frontend/js/__tests__/**',
        '**/*.test.js',
        '**/*.spec.js',
        '**/setup.js'
      ]
    },
    // Mock static assets
    mockReset: true,
    restoreMocks: true
  }
})
