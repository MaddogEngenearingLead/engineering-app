import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const here = (p) => fileURLToPath(new URL(p, import.meta.url));

// The legacy static pages live in this folder, so the React entry HTML is public/index.html.
export default defineConfig({
  root: here('./public'),
  plugins: [react()],
  css: { postcss: here('./') },
  server: {
    fs: { allow: [here('./')] },
    proxy: { '/api': 'http://localhost:8000' },
  },
  build: { outDir: here('./dist'), emptyOutDir: true },
});
