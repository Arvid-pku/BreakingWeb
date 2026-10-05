import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const serverPort = Number(process.env.VITE_SERVER_PORT) || 4175;
const backendUrl = `http://127.0.0.1:${process.env.VITE_BACKEND_PORT || 8080}`;

export default defineConfig({
  plugins: [react()],
  base: "/env/patient_portal/",
  optimizeDeps: { exclude: ["@breakingweb/shared", "@breakingweb/patient_portal"] },
  build: { outDir: "../../static/envs/patient_portal", emptyOutDir: true },
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
