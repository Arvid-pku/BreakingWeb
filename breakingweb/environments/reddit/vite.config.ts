import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const serverPort = Number(process.env.VITE_SERVER_PORT) || 4176;
const backendUrl = `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || 8080}`;

export default defineConfig({
  plugins: [react()],
  base: "/env/reddit/",
  optimizeDeps: {
    exclude: ["@breakingweb/shared", "@breakingweb/reddit"],
  },
  build: {
    outDir: "../../static/envs/reddit",
    emptyOutDir: true,
  },
  server: {
    port: serverPort,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": backendUrl,
      "/manifest": backendUrl,
      "/static": backendUrl,
      "/launch": backendUrl,
      "/control": backendUrl,
    },
  },
});
