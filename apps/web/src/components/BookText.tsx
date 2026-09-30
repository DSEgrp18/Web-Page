/**
 * Words from the book inside the interface's words.
 *
 * The book is never translated. Wherever its text appears — a sentence, an
 * answer's quote, a quiz option — it is marked `lang="si"`, so a screen reader
 * reading an English interface switches to its Sinhala voice for those words
 * and back again after them. Without it, NVDA reads Sinhala with an English
 * synthesiser, which is unintelligible.
 */

import { scriptLang } from "@/lib/i18n";

/** A character no string of ours contains, marking where the book's words go. */
const SLOT = "";

/**
 * An interface sentence with the book's words in it, marking only those words.
 *
 * `format` is the dictionary's own function (`strings.correctIs`), so the
 * sentence stays in one piece for translators and the words land where each
 * language puts them.
 */
export function Quoted({ format, text }: { format: (value: string) => string; text: string }) {
  const [before = "", after = ""] = format(SLOT).split(SLOT);
  return (
    <>
      {before}
      <span lang="si">{text}</span>
      {after}
    </>
  );
}

/**
 * A name a person typed — a book's title, a question — in whichever script
 * they typed it. Sinhala is marked Sinhala and Latin is marked English, so
 * neither is read with the other language's voice.
 */
export function Typed({ text }: { text: string }) {
  return <span lang={scriptLang(text)}>{text}</span>;
}
