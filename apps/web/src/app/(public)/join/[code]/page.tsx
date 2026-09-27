import { redirect } from "next/navigation";

/**
 * A class link: `/join/12345678` opens the join form with the code filled in.
 *
 * Joining still asks, and still waits for the teacher: this only saves typing
 * eight digits. The consent to share progress is never filled in by a link.
 * Only digits are carried over, so a crafted link cannot put anything else in
 * the field. Signed out, the classes page asks for sign-in first and comes
 * back here with the code.
 */
export default async function JoinPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  const digits = decodeURIComponent(code).replace(/\D/g, "").slice(0, 8);
  redirect(digits ? `/classes?code=${digits}` : "/classes");
}
