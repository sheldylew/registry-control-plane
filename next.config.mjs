const internalApiBaseUrl =
  process.env.INTERNAL_API_BASE_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${internalApiBaseUrl}/api/:path*`,
      },
      {
        source: "/auth/token",
        destination: `${internalApiBaseUrl}/auth/token`,
      },
      {
        source: "/healthz",
        destination: `${internalApiBaseUrl}/healthz`,
      },
    ];
  },
};

export default nextConfig;
