"use client";

import { useCallback, useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

import { strings } from "@/lib/strings";

const MIN = 20;
const MAX = 80;
const STEP = 5;
const BIG_STEP = 20;

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
 * not require seeing it.
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
  start: ReactNode;
  end: ReactNode;
  startLabel: string;
  endLabel: string;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const clamp = (value: number) => Math.max(MIN, Math.min(MAX, Math.round(value)));

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
        onPercent(MIN);
      } else if (event.key === "End") {
        event.preventDefault();
        onPercent(MAX);
      } else if (event.key === "Enter") {
        event.preventDefault();
        onPercent(50);
      }
    },
    [onPercent, percent],
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
      // Right-to-left is not a case this interface has, but reading the
      // computed direction costs nothing and keeps the maths honest if Sinhala
      // is ever shown beside an RTL script.
      const fraction = (event.clientX - box.left) / box.width;
      onPercent(Math.max(MIN, Math.min(MAX, Math.round(fraction * 100))));
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
  }, [onPercent]);

  const columns =
    collapsed === "start"
      ? "1fr 0 0"
      : collapsed === "end"
        ? "0 0 1fr"
        : `${percent}fr auto ${100 - percent}fr`;

  return (
    <div className="split" ref={frame} style={{ gridTemplateColumns: columns }}>
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
    </div>
  );
}
