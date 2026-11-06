import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { devHostBridge } from "./dev-host/plugin.js";

// The dev host bridge is DEV ONLY: it proxies the daemon RPC with the token held
// server-side so Studio's live mode works during development. Disable with
// ATOMC_STUDIO_DEV_HOST=0.
const enableDevHost = process.env.ATOMC_STUDIO_DEV_HOST !== "0";

export default defineConfig({
  plugins: [react(), ...(enableDevHost ? [devHostBridge()] : [])],
  server: { host: "127.0.0.1", port: 4178, strictPort: true },
  preview: { host: "127.0.0.1", port: 4189, strictPort: true },
  build: { target: "es2022", sourcemap: true },
});
