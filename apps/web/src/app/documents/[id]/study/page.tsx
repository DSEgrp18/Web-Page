import { Study } from "@/components/Study";

/** The book stays private to the browser identity held by ReaderProvider. */
export default async function StudyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <Study documentId={id} />;
}
