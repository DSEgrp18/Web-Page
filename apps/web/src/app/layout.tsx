import type { Metadata, Viewport } from "next";
import { Noto_Sans_Sinhala, Plus_Jakarta_Sans, Yaldevi } from "next/font/google";

import { LocaleProvider } from "@/components/LocaleProvider";
import { getLocale, getStrings } from "@/lib/i18n.server";
import { ICONS } from "@/lib/icons";
import { getTheme } from "@/lib/theme.server";

import "./globals.css";
import { Providers } from "./providers";

/*
 * Three faces, each with one job:
 *   Yaldevi            headings and the large display lines. Geometric and
 *                      rounded like the logo's lettering, with Sinhala and Latin.
 *   Noto Sans Sinhala  everything a reader reads and every control. The most
 *                      legible Sinhala on screen, at every size.
 *   Plus Jakarta Sans  Latin in the interface: English, numbers, page counts.
 *
 * Each `variable` is a *face*; globals.css builds the stack from it. A custom
 * property defined in terms of itself is invalid, which is how a face once
 * went unused.
 */
const yaldevi = Yaldevi({
  subsets: ["sinhala", "latin"],
  weight: ["600", "700"],
  variable: "--font-display-face",
  display: "swap",
});

const notoSansSinhala = Noto_Sans_Sinhala({
  subsets: ["sinhala", "latin"],
  // Only the weights the stylesheet sets. A weight nothing uses is a download
  // for every reader, and one more file Google may have to generate on the fly
  // (a `kit` URL, which next/font's dev bundler cannot resolve).
  weight: ["400", "600", "700"],
  variable: "--font-ui",
  display: "swap",
});

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "600", "700", "800"],
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
      className={`${yaldevi.variable} ${notoSansSinhala.variable} ${plusJakarta.variable}`}
    >
      <body>
        {/* Without script nothing would ever lift the loading screen, so it
            is never drawn at all. */}
        <noscript>
          <style>{".loading-screen{display:none}"}</style>
        </noscript>
        <LocaleProvider locale={locale}>
          <Providers>{children}</Providers>
        </LocaleProvider>
      </body>
    </html>
  );
}
