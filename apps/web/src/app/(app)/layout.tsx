import type { ReactNode } from "react";

import { AppFrame } from "@/components/AppFrame";

/** The product: every page here needs a session, and AppFrame asks for one. */
export default function AppLayout({ children }: { children: ReactNode }) {
  return <AppFrame>{children}</AppFrame>;
}
