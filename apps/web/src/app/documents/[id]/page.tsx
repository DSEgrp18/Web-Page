import { Reader } from "@/components/Reader";

/**
 * Route params arrive as a promise in Next 16. Nothing here renders on the
 * server beyond the id: the document itself is private, and fetching it needs
 * the reader's identity, which lives in the browser.
 */
export default async function ReaderPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ segment?: string | string[] }>;
}) {
  const { id } = await params;
  const { segment } = await searchParams;
  return (
    <Reader documentId={id} bookmarkSegmentId={typeof segment === "string" ? segment : undefined} />
  );
}
