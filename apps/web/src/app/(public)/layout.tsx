import type { ReactNode } from "react";

import { PublicFrame } from "@/components/PublicFrame";

/**
 * The public site: the front door, the statements a service like this owes its
 * readers, and the account pages. Nothing here needs a session, and every
 * page renders statically.
 */
export default function PublicLayout({ children }: { children: ReactNode }) {
  return <PublicFrame>{children}</PublicFrame>;
}
