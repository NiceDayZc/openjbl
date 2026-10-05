import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The built page ships inside the Python package and is served by openjbl-gui;
// `npm run dev` proxies the API to a running `openjbl-gui --no-browser`.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, './src') } },
  base: './',
  build: { outDir: '../src/openjbl/web', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:47800' } },
})
