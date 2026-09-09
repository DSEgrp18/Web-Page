import type { Metadata, Viewport } from "next";

import { AppFrame } from "@/components/AppFrame";
import { strings } from "@/lib/strings";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: strings.appName,
  description: strings.appTagline,
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Never cap zoom. A low-vision reader magnifying the page is the point.
  maximumScale: 5,
  userScalable: true,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  // `lang="si"` is not cosmetic: it is what tells NVDA and TalkBack to use a
  // Sinhala voice for the interface. Without it the controls are read out by an
  // English synthesiser, which is unintelligible even when the words are right.
  return (
    <html lang="si">
      <body>
        <Providers>
          <AppFrame>{children}</AppFrame>
        </Providers>
      </body>
    </html>
  );
}
