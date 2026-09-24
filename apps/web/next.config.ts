/**
 * The reader is a browser application. The server renders the public pages
 * statically, forwards `/api` to the reader API (`src/app/api/[...path]`), and
 * sends a signed-in visitor from `/` to the library (`src/proxy.ts`).
 */
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,

  async redirects() {
    return [
      // The reader moved under /library. Permanent, so a saved bookmark link
      // keeps working and a browser learns the new address; the query string
      // (?segment=) goes with it.
      { source: "/documents/:id", destination: "/library/:id", permanent: true },
      // The study page was replaced by the assistant beside the book.
      { source: "/documents/:id/study", destination: "/library/:id", permanent: true },
    ];
  },
};

export default nextConfig;
