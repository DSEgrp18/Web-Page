import type { Metadata, Viewport } from "next";
import { Abhaya_Libre, Noto_Sans_Sinhala, Roboto } from "next/font/google";

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

const roboto = Roboto({
  subsets: ["latin"],
  // Roboto ships 100/300/400/500/700/900; 600 is not one of them and
  // next/font fails the build rather than rounding to the nearest.
  weight: ["400", "500", "700"],
  variable: "--font-latin",
  display: "swap",
});

export const metadata: Metadata = {
  // `%s — ස්වර` so a browser tab and a screen-reader title both say which book
  // is open before they say which product it is open in.
  title: { default: `${strings.appName} — ${strings.appTagline}`, template: `%s — ${strings.appName}` },
  description: strings.appTagline,
  applicationName: strings.appNameLatin,
  icons: {
    icon: [
      { url: "/brand/icon.png", sizes: "64x64", type: "image/png" },
      { url: "/brand/swara-icon.webp", sizes: "512x512", type: "image/webp" },
    ],
    apple: "/brand/swara-icon.webp",
  },
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
      className={`${abhayaLibre.variable} ${notoSansSinhala.variable} ${roboto.variable}`}
    >
      <body>
        <Providers>
          <AppFrame>{children}</AppFrame>
        </Providers>
      </body>
    </html>
  );
}
