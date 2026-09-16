import type { NextConfig } from "next";

// standalone output keeps the Docker image small and is what deploy/compose.yml expects
// (see docs/TIMEOS_ENGINEERING_SPEC.md §29 Deployment).
//
// The rewrite makes browser-side calls to /v1/* same-origin against this Next.js server, which
// then proxies to the backend. This mirrors exactly what Caddy does in production (Caddyfile:
// "handle /v1/* { reverse_proxy api:8000 }") — one origin for both the dashboard and the API, so
// the session/CSRF cookies §28 requires (httpOnly, SameSite=Strict) work identically in dev and
// prod without ever needing CORS. Server COMPONENTS (which run in Node, not the browser) don't
// go through this — they call BACKEND_INTERNAL_URL directly (see lib/api.ts).
const BACKEND_URL = process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/v1/:path*", destination: `${BACKEND_URL}/v1/:path*` }];
  },
};

export default nextConfig;
