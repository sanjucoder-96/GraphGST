import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Vite config for the Graph GST investigator console.
// Dev server on :5173. Backend expected at :8000; api.ts handles fallback.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    host: '127.0.0.1'
  },
  build: {
    target: 'es2022',
    sourcemap: true,
    outDir: 'dist',
    emptyOutDir: true
  }
});
