import type { NextConfig } from "next";

const engine = process.env.ENGINE_URL ?? "http://127.0.0.1:18771";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/engine/:path*", destination: `${engine}/:path*` }];
  },
};

export default nextConfig;
