import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const serverPort = Number(process.env.VITE_SERVER_PORT) || 8084;
const backendUrl = `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || 8080}`;

export default defineConfig({
  plugins: [react()],
  base: "/env/booking/",
  optimizeDeps: {
    exclude: ["@breakingweb/shared", "@breakingweb/booking"],
  },
  build: {
    outDir: "../../static/envs/booking",
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
