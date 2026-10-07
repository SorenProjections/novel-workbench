import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  build: {
    outDir: '../server/src/novelwb/web',
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    port: 5173,
    proxy: {
      '/projects': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/settings': 'http://127.0.0.1:8000',
    },
  },
});
