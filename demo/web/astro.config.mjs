// @ts-check
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

// The site is static and calls the API on its own origin under /api: the dev server
// proxies it, and in Docker nginx does. Nothing in the build knows the API's address.
export default defineConfig({
  integrations: [react()],
  server: { port: 4400 },
  vite: {
    server: {
      strictPort: true,
      proxy: {
        '/api': {
          target: process.env.API_PROXY_TARGET ?? 'http://localhost:8100',
          changeOrigin: true,
        },
      },
    },
  },
});
