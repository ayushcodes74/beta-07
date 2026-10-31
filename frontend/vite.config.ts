import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/react/") || id.includes("/node_modules/react-dom/") || id.includes("/node_modules/scheduler/")) return "react-vendor";
          if (id.includes("/node_modules/recharts/") || id.includes("/node_modules/victory-vendor/") || /\/node_modules\/d3-[^/]+\//.test(id)) return "charts";
          if (id.includes("/node_modules/framer-motion/")) return "motion";
          if (id.includes("/node_modules/lucide-react/")) return "icons";
          if (id.includes("/node_modules/@radix-ui/")) return "ui-vendor";
          if (id.includes("/node_modules/")) return "vendor";
        },
      },
    },
  },
});
