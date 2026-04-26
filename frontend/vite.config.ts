import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vitejs.dev/config/
//
// PWA plugin gating:
// `vite-plugin-pwa` is intentionally only registered for production
// builds (`command === 'build'`). Enabling it in `vite dev` causes
// Workbox to recursively scan `globPatterns` against an in-flight
// esbuild dependency graph, which on this codebase pinned a single
// esbuild service to ~400% CPU sustained (see commit message for
// before/after measurements). The deployed PWA is unaffected because
// `yarn build` runs with `command === 'build'` and the plugin is
// included exactly as before.
export default defineConfig(({ command }) => ({
  plugins: [
    react(),
    tailwindcss(),
    ...(command === 'build'
      ? [
          VitePWA({
            registerType: 'autoUpdate',
            // Include all built assets in the precache manifest
            includeAssets: ['**/*.{js,css,html,svg,png,ico,woff,woff2}'],
            manifest: false, // We manage manifest.json ourselves in public/
            workbox: {
              // Service worker output filename
              swDest: 'dist/sw.js',
              // Precache everything emitted by the build
              globPatterns: ['**/*.{js,css,html,svg,png,ico,woff,woff2}'],
              runtimeCaching: [
                // Orders — NetworkFirst with a 5-minute stale fallback
                {
                  urlPattern: /\/api\/v1\/orders/,
                  handler: 'NetworkFirst',
                  options: {
                    cacheName: 'api-orders',
                    networkTimeoutSeconds: 10,
                    expiration: {
                      maxEntries: 200,
                      maxAgeSeconds: 5 * 60, // 5 minutes
                    },
                    cacheableResponse: {
                      statuses: [0, 200],
                    },
                  },
                },
                // Materials — NetworkFirst with a 10-minute stale fallback
                {
                  urlPattern: /\/api\/v1\/materials/,
                  handler: 'NetworkFirst',
                  options: {
                    cacheName: 'api-materials',
                    networkTimeoutSeconds: 10,
                    expiration: {
                      maxEntries: 500,
                      maxAgeSeconds: 10 * 60, // 10 minutes
                    },
                    cacheableResponse: {
                      statuses: [0, 200],
                    },
                  },
                },
                // Activities — CacheFirst; these change rarely (hourly revalidation)
                {
                  urlPattern: /\/api\/v1\/activities/,
                  handler: 'CacheFirst',
                  options: {
                    cacheName: 'api-activities',
                    expiration: {
                      maxEntries: 100,
                      maxAgeSeconds: 60 * 60, // 1 hour
                    },
                    cacheableResponse: {
                      statuses: [0, 200],
                    },
                  },
                },
                // All other API routes — NetworkOnly (never cache mutations or auth)
                {
                  urlPattern: /\/api\//,
                  handler: 'NetworkOnly',
                },
                // Static assets (JS, CSS, fonts) — CacheFirst
                {
                  urlPattern: /\.(js|css|woff2?)(\?.*)?$/,
                  handler: 'CacheFirst',
                  options: {
                    cacheName: 'static-assets',
                    expiration: {
                      maxEntries: 100,
                      maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
                    },
                  },
                },
              ],
            },
          }),
        ]
      : []),
  ],
  server: {
    host: '0.0.0.0',
    port: 3000,
    // Defensive: prevent the dev file watcher from descending into
    // huge / irrelevant trees. Without this, chokidar will happily
    // watch node_modules and .git, which contributed to the runaway
    // esbuild rebuild loop diagnosed alongside the PWA gating fix.
    watch: {
      ignored: [
        '**/node_modules/**',
        '**/.git/**',
        '**/dist/**',
        '**/playwright-report/**',
        '**/test-results/**',
        '**/.yarn/**',
        '**/coverage/**',
      ],
    },
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8080',
        changeOrigin: true,
        secure: false,
      },
      '/ws': {
        target: process.env.VITE_WS_TARGET || 'ws://localhost:8080',
        ws: true,
        changeOrigin: true,
      },
      '/uploads': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8080',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
}))
