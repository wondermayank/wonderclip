import type { NextConfig } from "next";

/**
 * Wonder Clips website: a fully static site (Cloudflare Pages).
 * All processing happens in the Wonder Clips engine on the visitor's own computer
 * (http://127.0.0.1:8000), so there is no server-side code.
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
