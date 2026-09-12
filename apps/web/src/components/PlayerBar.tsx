"use client";

import { useId } from "react";

import { strings } from "@/lib/strings";
import type { usePlayer } from "@/lib/usePlayer";

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/**
 * The player, along the bottom, always there.
 *
 * ## A group, not a toolbar
 *
 * `role="toolbar"` takes over the arrow keys. A screen-reader user is already
 * using those to move through the text, and a control strip that swallows them
 * makes the page harder to read than having no strip at all. Every control here
 * is a plain button reached by Tab.
 *
 * ## No single-key shortcuts
 *
 * `p`, `n`, and space collide with NVDA's browse-mode quick navigation, where
 * single letters jump between elements. Shortcuts can be added later, scoped
 * and tested with a real screen reader — not guessed at now.
 *
 * ## There is no seek bar, because there is nothing true to put on it
 *
 * The API gives a duration per segment only once that segment's audio exists,
 * and nothing gives a position within a book. A scrubber across a whole
 * chapter would be a control that looks precise and is not. What is shown
 * instead is the honest thing: which sentence, out of how many.
 */
export function PlayerBar({
  player,
  disabled,
  position,
  total,
  bookmarkLabel,
  bookmarkSaving,
  onBookmark,
}: {
  player: ReturnType<typeof usePlayer>;
  disabled: boolean;
  /** 1-based index of the sentence cued or playing; 0 when there is none. */
  position: number;
  total: number;
  bookmarkLabel: string;
  bookmarkSaving: boolean;
  onBookmark: () => void;
}) {
  const speedId = useId();
  const playing = player.status === "playing";
  const busy = player.status === "loading";

  return (
    <div className="player" role="group" aria-label={strings.playerLabel}>
      <div className="player-transport">
        <button
          type="button"
          className="btn btn-quiet btn-icon"
          onClick={player.previous}
          disabled={disabled}
        >
          <PrevIcon />
          <span className="visually-hidden">{strings.previousSentence}</span>
        </button>

        <button
          type="button"
          className="btn btn-primary btn-icon player-play"
          onClick={player.toggle}
          disabled={disabled}
        >
          {busy ? <SpinnerIcon /> : playing ? <PauseIcon /> : <PlayIcon />}
          <span className="visually-hidden">
            {busy ? strings.loadingAudio : playing ? strings.pause : strings.play}
          </span>
        </button>

        <button
          type="button"
          className="btn btn-quiet btn-icon"
          onClick={player.next}
          disabled={disabled}
        >
          <NextIcon />
          <span className="visually-hidden">{strings.nextSentence}</span>
        </button>

        <button
          type="button"
          className="btn btn-quiet btn-sm"
          onClick={player.stop}
          disabled={disabled || player.status === "idle"}
        >
          {strings.stop}
        </button>
      </div>

      {/*
       * Where we are, stated rather than drawn. `aria-live="off"`: this changes
       * every sentence, and the player already announces the sentence itself —
       * a live region here would say the number over the words.
       */}
      <p className="player-position" aria-live="off">
        {busy ? (
          <span className="hint">{strings.buffering}</span>
        ) : total > 0 && position > 0 ? (
          <span className="latin">{strings.playbackPosition(position, total)}</span>
        ) : null}
      </p>

      <div className="player-tools">
        <button
          type="button"
          className="btn btn-quiet btn-sm"
          onClick={onBookmark}
          disabled={disabled || !player.currentId || bookmarkSaving}
        >
          <BookmarkIcon />
          {bookmarkLabel}
        </button>

        <label htmlFor={speedId} className="visually-hidden">
          {strings.speed}
        </label>
        <select
          id={speedId}
          className="player-speed"
          value={String(player.rate)}
          onChange={(event) => player.setRate(Number(event.target.value))}
        >
          {SPEEDS.map((speed) => (
            <option key={speed} value={String(speed)}>
              {speed}×
            </option>
          ))}
        </select>
      </div>

      {player.realModel === false ? (
        <p className="player-warning">
          <strong>{strings.placeholderAudioHeading}</strong>
        </p>
      ) : null}
    </div>
  );
}

function PlayIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M8 5.5v13l10-6.5-10-6.5Z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 5h3.2v14H7zM13.8 5H17v14h-3.2z" fill="currentColor" />
    </svg>
  );
}

function PrevIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M17 5.5v13L8 12l9-6.5ZM6 5h2v14H6z" fill="currentColor" />
    </svg>
  );
}

function NextIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 5.5 16 12l-9 6.5v-13ZM16 5h2v14h-2z" fill="currentColor" />
    </svg>
  );
}

function BookmarkIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M6.5 4.5h11v15l-5.5-4-5.5 4v-15Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Spins under CSS, and holds still under prefers-reduced-motion. */
function SpinnerIcon() {
  return (
    <svg
      className="spinner"
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="12" cy="12" r="8" stroke="currentColor" strokeWidth="2.5" opacity="0.25" />
      <path
        d="M20 12a8 8 0 0 0-8-8"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
