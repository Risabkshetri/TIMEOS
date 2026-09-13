import type { NextConfig } from "next";

// standalone output keeps the Docker image small and is what deploy/compose.yml expects
// (see docs/TIMEOS_ENGINEERING_SPEC.md §29 Deployment).
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
