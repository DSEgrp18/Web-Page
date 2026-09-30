import type { Metadata, Viewport } from "next";
import { Abhaya_Libre, Noto_Sans_Sinhala, Roboto } from "next/font/google";

import { LocaleProvider } from "@/components/LocaleProvider";
import { getLocale, getStrings } from "@/lib/i18n.server";
import { ICONS } from "@/lib/icons";
import { getTheme } from "@/lib/theme.server";

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
  // Not `--font-latin`: globals.css builds that stack from this, and a
  // property defined in terms of itself is invalid, so the face went unused.
  variable: "--font-latin-face",
  display: "swap",
});

export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return {
    // `%s — ස්වර` so a browser tab and a screen-reader title both say which
    // book is open before they say which product it is open in.
    title: {
      default: `${strings.appName} — ${strings.appTagline}`,
      template: `%s — ${strings.appName}`,
    },
    description: strings.appTagline,
    applicationName: strings.appNameLatin,
    icons: ICONS,
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  // Never cap zoom. A low-vision reader magnifying the page is the point.
  maximumScale: 5,
  userScalable: true,
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // `lang` is not cosmetic: it is what tells NVDA and TalkBack which voice to
  // use for the interface. Sinhala controls read by an English synthesiser are
  // unintelligible even when the words are right. It follows the reader's
  // language cookie, read here on the server, so the first byte is right.
  const locale = await getLocale();
  // The theme cookie, likewise, so a reader who chose dark gets dark from the
  // first paint. `system` leaves it to `prefers-color-scheme`.
  const theme = await getTheme();
  return (
    <html
      lang={locale}
      data-theme={theme === "system" ? undefined : theme}
      className={`${abhayaLibre.variable} ${notoSansSinhala.variable} ${roboto.variable}`}
    >
      <body>
        <LocaleProvider locale={locale}>
          <Providers>{children}</Providers>
        </LocaleProvider>
      </body>
    </html>
  );
}
