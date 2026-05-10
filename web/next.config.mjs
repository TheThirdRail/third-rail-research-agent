/** @type {import('next').NextConfig} */
const nextConfig = {
    output: "standalone",
    images: {
        unoptimized: true,
    },
    eslint: {
        // Standalone `npm run lint` handles linting with flat config.
        // Next 15's built-in integration passes removed ESLint 8 options.
        ignoreDuringBuilds: true,
    },
};

export default nextConfig;
