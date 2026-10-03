import type { Strings } from "./strings";

/** Format for reset notices and library dates without relying on `si-LK` locale data. */
export function formatDateTime(iso: string, strings: Strings): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return strings.formatDateTime(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
    date.getHours(),
    date.getMinutes(),
  );
}
