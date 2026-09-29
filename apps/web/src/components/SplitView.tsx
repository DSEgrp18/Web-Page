"use client";

import { useCallback, useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";
import { useStrings } from "@/components/LocaleProvider";

const MIN = 20;
const MAX = 80;
const STEP = 5;
const BIG_STEP = 20;

/** The narrowest a panel may be, in rem: a PDF page or a line of Sinhala under
 * this is not worth having beside the other. Rem, so text zoom raises it. */
export const PANEL_MIN_REM = 18;

/** A drag that ends within this many points of an even split lands on it. */
const SNAP = 3;

function rootPx(): number {
  if (typeof window === "undefined") return 16;
  return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
}

/**
 * Two panels and a divider you can actually move.
 *
 * ## The divider is a real control, not a decoration you drag
 *
 * `role="separator"` with `aria-valuenow` and a tabindex, which is what makes
 * it a thing a keyboard reader can find, understand, and operate: arrows move
 * it 5% at a time, Page Up/Down 20%, Home/End go to the extremes, and Enter
 * returns it to an even split. A drag handle with no keyboard path is the
 * commonest way a resizable layout becomes unusable without a mouse.
 *
 * The percentage is announced, so "how wide is this" has an answer that does
 * not require seeing it. Double-click also returns it to an even split, and a
 * drag that ends near the middle lands on it.
 *
 * ## Neither panel goes below PANEL_MIN_REM
 *
 * The extremes a key or a drag can reach are worked out from the width there
 * is, not fixed at 20–80%. When there is not room for two panels at that
 * width, `onNarrow` says so, and the reader shows them as tabs instead.
 *
 * ## Dragging listens on the window, not the handle
 *
 * A pointer moving faster than React re-renders will leave the handle behind,
 * and a `mousemove` bound to the handle stops firing the moment it does.
 * Pointer capture plus window listeners means the drag survives the pointer
 * outrunning it, and ends even if the button is released over another element.
 */
export function SplitView({
  percent,
  onPercent,
  collapsed,
  onRestore,
  onNarrow,
  start,
  end,
  startLabel,
  endLabel,
}: {
  /** How much of the width the first panel gets, 20–80. */
  percent: number;
  onPercent: (next: number) => void;
  /** When set, one panel has the whole width and the divider is gone. */
  collapsed: "start" | "end" | null;
  /** Bring back the panel that `collapsed` hid. */
  onRestore?: () => void;
  /** Told whether two panels still fit side by side at their minimum width. */
  onNarrow?: (narrow: boolean) => void;
  start: ReactNode;
  end: ReactNode;
  startLabel: string;
  endLabel: string;
}) {
  const strings = useStrings();
  const frame = useRef<HTMLDivElement>(null);
  const divider = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const restoring = useRef(false);

  /** The extremes, in percent, that keep both panels at least PANEL_MIN_REM. */
  const limits = useCallback((): [number, number] => {
    const width = frame.current?.getBoundingClientRect().width ?? 0;
    if (width <= 0) return [MIN, MAX];
    const least = Math.ceil(((PANEL_MIN_REM * rootPx()) / width) * 100);
    const low = Math.min(50, Math.max(MIN, least));
    return [low, 100 - low];
  }, []);

  const clamp = useCallback(
    (value: number) => {
      const [low, high] = limits();
      return Math.max(low, Math.min(high, Math.round(value)));
    },
    [limits],
  );

  const onKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      const moves: Record<string, number> = {
        ArrowLeft: -STEP,
        ArrowRight: STEP,
        PageUp: -BIG_STEP,
        PageDown: BIG_STEP,
      };
      if (event.key in moves) {
        event.preventDefault();
        onPercent(clamp(percent + moves[event.key]!));
      } else if (event.key === "Home") {
        event.preventDefault();
        onPercent(limits()[0]);
      } else if (event.key === "End") {
        event.preventDefault();
        onPercent(limits()[1]);
      } else if (event.key === "Enter") {
        event.preventDefault();
        onPercent(50);
      }
    },
    [clamp, limits, onPercent, percent],
  );

  const onPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    dragging.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  useEffect(() => {
    const move = (event: PointerEvent) => {
      if (!dragging.current) return;
      const box = frame.current?.getBoundingClientRect();
      if (!box || box.width === 0) return;
      const at = ((event.clientX - box.left) / box.width) * 100;
      // A soft snap: near the middle is the middle, so an even split does not
      // take a steady hand. Keys already step through 50.
      onPercent(Math.abs(at - 50) <= SNAP ? 50 : clamp(at));
    };
    const stop = () => {
      dragging.current = false;
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
  }, [clamp, onPercent]);

  // Whether two panels fit. jsdom has no ResizeObserver, and a browser
  // without one keeps the split it has: the media query still makes tabs of
  // a phone.
  useEffect(() => {
    const element = frame.current;
    if (!element || !onNarrow || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const width = entry?.contentRect.width ?? 0;
      if (width > 0) onNarrow(width < 2 * PANEL_MIN_REM * rootPx() + 16);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [onNarrow]);

  // The restore bar goes with the press that used it; focus goes to the
  // divider that replaced it, not to the top of the page.
  useEffect(() => {
    if (!collapsed && restoring.current) {
      restoring.current = false;
      divider.current?.focus();
    }
  }, [collapsed]);

  // One column when collapsed. The hidden panel is `display: none` and the
  // divider is not rendered, so the visible panel is the only grid item and
  // lands in the first track. "0 0 1fr" gave it a 0-wide track, and expanding
  // the reading panel showed nothing at all.
  const floor = `${PANEL_MIN_REM}rem`;
  const columns = collapsed
    ? collapsed === "start"
      ? "minmax(0, 1fr) auto"
      : "auto minmax(0, 1fr)"
    : `minmax(${floor}, ${percent}fr) auto minmax(${floor}, ${100 - percent}fr)`;

  const restore =
    collapsed && onRestore ? (
      <button
        type="button"
        className="split-restore"
        data-side={collapsed === "start" ? "end" : "start"}
        onClick={() => {
          restoring.current = true;
          onRestore();
        }}
      >
        {/* Names the panel it brings back: the toolbar's own button already
            says "both panels", and two controls should not share a name. */}
        <span className="split-restore-label">
          {strings.restorePanel(collapsed === "start" ? endLabel : startLabel)}
        </span>
      </button>
    ) : null;

  return (
    <div className="split" ref={frame} style={{ gridTemplateColumns: columns }}>
      {collapsed === "end" ? restore : null}

      <div className="split-panel" data-hidden={collapsed === "end"}>
        {start}
      </div>

      {collapsed ? null : (
        /*
         * A focusable separator is a real ARIA widget — the spec calls it a
         * "window splitter" and requires exactly this: a tabindex, arrow keys,
         * and aria-valuenow. `separator` is allowed a tabindex in
         * eslint.config.mjs for that reason; the interaction rule has no such
         * option, so it is disabled here.
         */
        // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
        <div
          ref={divider}
          className="split-divider"
          role="separator"
          tabIndex={0}
          aria-orientation="vertical"
          aria-label={strings.splitLabel}
          aria-valuenow={percent}
          aria-valuemin={MIN}
          aria-valuemax={MAX}
          aria-valuetext={`${startLabel} ${percent}%, ${endLabel} ${100 - percent}%`}
          onKeyDown={onKeyDown}
          onPointerDown={onPointerDown}
          onDoubleClick={() => onPercent(50)}
        >
          <span className="split-grip" aria-hidden="true" />
        </div>
      )}

      <div className="split-panel" data-hidden={collapsed === "start"}>
        {end}
      </div>

      {collapsed === "start" ? restore : null}
    </div>
  );
}
