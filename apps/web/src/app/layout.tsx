import type { Metadata, Viewport } from "next";
import { Abhaya_Libre, Manrope, Noto_Sans_Sinhala } from "next/font/google";

import { AppFrame } from "@/components/AppFrame";
import { strings } from "@/lib/strings";

import "./globals.css";
import { Providers } from "./providers";

const abhayaLibre = Abhaya_Libre({
  subsets: ["sinhala", "latin"],
  weight: ["400", "700"],
  variable: "--font-display",
  display: "swap",
});

const notoSansSinhala = Noto_Sans_Sinhala({
  subsets: ["sinhala", "latin"],
  weight: ["400", "600", "700"],
  variable: "--font-ui",
  display: "swap",
});

const manrope = Manrope({
  subsets: ["latin"],
  weight: ["400", "600", "700"],
  variable: "--font-latin",
  display: "swap",
});

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
    <html
      lang="si"
      className={`${abhayaLibre.variable} ${notoSansSinhala.variable} ${manrope.variable}`}
    >
      <body>
        <Providers>
          <AppFrame>{children}</AppFrame>
        </Providers>
      </body>
    </html>
  );
}
