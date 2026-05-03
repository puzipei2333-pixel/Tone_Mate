import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  ...(mode === "development"
    ? {
        server: {
          proxy: {
            "/api": {
              target: "http://127.0.0.1:8000",
              changeOrigin: true
            }
          }
        }
      }
    : {})
}));
