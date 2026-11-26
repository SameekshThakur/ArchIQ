import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'node:path';

// where /api is forwarded; the end-to-end tests point it at their own throw-away API so they never touch the development one
const API = process.env.ARCHIQ_API_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, 'src') },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: API, changeOrigin: true },
    },
  },
  build: {
    target: 'es2022',
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          radix: [
            '@radix-ui/react-dialog',
            '@radix-ui/react-popover',
            '@radix-ui/react-tabs',
            '@radix-ui/react-tooltip',
            '@radix-ui/react-dropdown-menu',
            '@radix-ui/react-scroll-area',
            '@radix-ui/react-switch',
            '@radix-ui/react-select',
            '@radix-ui/react-collapsible',
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    css: false,
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'], // Playwright specs run with `npm run e2e`
  },
});
