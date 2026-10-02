import type { Strings } from "./strings";

const PREFIX = "note:";

export function parsePipelineNote(
  note: string,
): { code: string; params: Record<string, string> } | null {
  if (!note.startsWith(PREFIX)) return null;
  const rest = note.slice(PREFIX.length);
  const cut = rest.indexOf("?");
  const code = cut === -1 ? rest : rest.slice(0, cut);
  const params: Record<string, string> = {};
  if (cut !== -1) {
    const query = new URLSearchParams(rest.slice(cut + 1));
    query.forEach((value, key) => {
      params[key] = value;
    });
  }
  return { code, params };
}

/** Interface copy for a pipeline note; English fallback only for old prose. */
export function formatPipelineNote(
  note: string,
  strings: Strings,
): { text: string; coded: boolean } {
  const parsed = parsePipelineNote(note);
  if (!parsed) return { text: note, coded: false };
  return { text: strings.pipelineNote(parsed.code, parsed.params), coded: true };
}
