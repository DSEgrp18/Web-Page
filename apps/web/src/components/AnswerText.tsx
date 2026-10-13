import { Fragment } from "react";

/**
 * A written answer, laid out for reading: paragraphs, and numbered or bulleted
 * lists as real lists.
 *
 * The answer is plain text, never markup: it is read aloud too, so the model
 * is asked for one list item per line and a blank line between paragraphs,
 * with no symbols that a voice would pronounce. This turns those lines into
 * structure. It builds elements, never HTML, so nothing in an answer can
 * inject markup.
 *
 * Older answers arrived as one line, "1. … 2. … 3. …". A run of two or more
 * markers counting up by one is split into a list as well. The book's own
 * numbers are kept: a list that starts at 4 starts at 4.
 */
export type AnswerBlock =
  | { kind: "paragraph"; text: string }
  | { kind: "numbered"; items: { number: number; text: string }[] }
  | { kind: "bulleted"; items: string[] };

const NUMBERED = /^(\d{1,3})[.)]\s+(.*)$/;
const BULLETED = /^[-•*]\s+(.*)$/;
// A marker inside a line: 1-3 digits, a full stop or bracket, then a space.
// "2.5" (no space) and a year such as "1971. " (four digits) are not markers.
const INLINE_MARKER = /(^|\s)(\d{1,3})[.)]\s+/g;

/** "1. A. 2. B." on one line, as separate lines, if it really is a list. */
function splitInlineList(line: string): string[] {
  const markers = [...line.matchAll(INLINE_MARKER)];
  if (markers.length < 2) return [line];
  const numbers = markers.map((match) => Number(match[2]));
  const counts = numbers.every((n, i) => i === 0 || n === numbers[i - 1]! + 1);
  if (!counts) return [line];
  const pieces: string[] = [];
  const first = markers[0]!.index! + markers[0]![1]!.length;
  const intro = line.slice(0, first).trim();
  if (intro) pieces.push(intro);
  markers.forEach((match, i) => {
    const start = match.index! + match[1]!.length;
    const end = i + 1 < markers.length ? markers[i + 1]!.index! : line.length;
    pieces.push(line.slice(start, end).trim());
  });
  return pieces;
}

export function answerBlocks(text: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  const paragraphs = text.replace(/\r\n?/g, "\n").split(/\n\s*\n/);
  for (const paragraph of paragraphs) {
    const lines = paragraph
      .split("\n")
      .flatMap((line) => splitInlineList(line.trim()))
      .filter(Boolean);
    for (const line of lines) {
      const last = blocks[blocks.length - 1];
      const numbered = NUMBERED.exec(line);
      const bulleted = BULLETED.exec(line);
      if (numbered) {
        const item = { number: Number(numbered[1]), text: numbered[2]! };
        if (last?.kind === "numbered") last.items.push(item);
        else blocks.push({ kind: "numbered", items: [item] });
      } else if (bulleted) {
        if (last?.kind === "bulleted") last.items.push(bulleted[1]!);
        else blocks.push({ kind: "bulleted", items: [bulleted[1]!] });
      } else {
        blocks.push({ kind: "paragraph", text: line });
      }
    }
    // A blank line ends a list, so the next paragraph's list starts afresh.
    blocks.push({ kind: "paragraph", text: "" });
  }
  return blocks.filter((block) => block.kind !== "paragraph" || block.text !== "");
}

export function AnswerText({ text }: { text: string }) {
  return (
    <>
      {answerBlocks(text).map((block, i) => (
        <Fragment key={i}>
          {block.kind === "paragraph" ? (
            <p>{block.text}</p>
          ) : block.kind === "numbered" ? (
            <ol start={block.items[0]!.number}>
              {block.items.map((item, j) => (
                // `value`, not just `start`: the book's numbers are kept even
                // where it skips or repeats one.
                <li key={j} value={item.number}>
                  {item.text}
                </li>
              ))}
            </ol>
          ) : (
            <ul>
              {block.items.map((item, j) => (
                <li key={j}>{item}</li>
              ))}
            </ul>
          )}
        </Fragment>
      ))}
    </>
  );
}
