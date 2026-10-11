import { defineConfig } from "vite";

// Static build for Cloudflare Pages. The API base is injected at build time
// (VITE_API_BASE); defaults to same-origin `/v1` for a proxied deployment.
export default defineConfig({
  build: { outDir: "dist", sourcemap: true },
  define: {
    __API_BASE__: JSON.stringify(process.env.VITE_API_BASE || "/v1"),
  },
});
