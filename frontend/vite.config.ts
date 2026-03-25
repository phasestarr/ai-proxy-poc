/**
 * Purpose:
 * - Configure frontend build behavior.
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
