/**
 * The reader is a browser application talking to a separate FastAPI service,
 * so nothing here renders on a server. Keeping that explicit avoids a whole
 * class of confusion later about where a request is actually made from.
 *
 * @type {import('next').NextConfig}
 */
const nextConfig = {
  reactStrictMode: true,
  // Type and lint errors fail `npm run typecheck` and `npm run lint` in CI as
  // their own jobs. Letting the build fail on them too would report the same
  // problem three times with the least useful message of the three first.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
