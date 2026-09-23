/**
 * The reader is a browser application talking to a separate FastAPI service,
 * so nothing here renders on a server. Keeping that explicit avoids a whole
 * class of confusion later about where a request is actually made from.
 *
 * @type {import('next').NextConfig}
 */
const nextConfig = {
  reactStrictMode: true,
};

export default nextConfig;
