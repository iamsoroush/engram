import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const allowedHosts = process.env.VITE_ALLOWED_HOSTS
  ? process.env.VITE_ALLOWED_HOSTS.split(",").map((host) => host.trim()).filter(Boolean)
  : [];

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts,
    proxy: {
      "/api/v1": process.env.VITE_PROXY_TARGET || "http://localhost:8000",
    },
  },
});
