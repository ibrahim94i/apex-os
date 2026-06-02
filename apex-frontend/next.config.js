/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // standalone only for Docker/Railway — Vercel uses its own Next.js runtime
  ...(process.env.VERCEL ? {} : { output: "standalone" }),
};

module.exports = nextConfig;
