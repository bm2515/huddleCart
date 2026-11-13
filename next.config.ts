import type { NextConfig } from "next";

// Locally the Python agent runs on its own port. On Vercel it is the api/index.py function.
const agentUrl =
  process.env.AGENT_URL ?? (process.env.VERCEL ? "" : "http://localhost:8000");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: agentUrl ? `${agentUrl}/api/:path*` : "/api/index" }];
  },
};

export default nextConfig;
