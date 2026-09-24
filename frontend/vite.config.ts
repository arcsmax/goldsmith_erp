import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'
import { buildRuntimeCaching } from './src/pwa/cachingRules'

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
              // FE-09 / FE-11 (W1-14): no /api/ response that can carry
              // customer PII, financial data, design IP or insurance
              // valuations may be cached — see src/pwa/cachingRules.ts for
              // the full rationale and the single source of truth these
              // rules are built from.
              runtimeCaching: buildRuntimeCaching(),
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
