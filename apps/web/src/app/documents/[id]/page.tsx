import { Reader } from "@/components/Reader";

/**
 * Route params arrive as a promise in Next 16. Nothing here renders on the
 * server beyond the id: the document itself is private, and fetching it needs
 * the reader's identity, which lives in the browser.
 */
export default async function ReaderPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Reader documentId={id} />;
}
