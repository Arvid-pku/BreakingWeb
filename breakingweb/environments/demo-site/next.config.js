/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "export",
  transpilePackages: ["@breakingweb/shared", "@breakingweb/gmail"],
  images: { unoptimized: true },
};

module.exports = nextConfig;
