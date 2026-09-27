"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { useAnnouncer } from "@/components/Announcer";
import {
  listSaved,
  offlineSupported,
  removeSaved,
  savedClip,
  type SavedChapter,
} from "@/lib/offline";
import { strings } from "@/lib/strings";

function megabytes(bytes: number): string {
  return (bytes / 1_000_000).toFixed(1);
}

/**
 * Chapters saved on this device, and a player for them that needs no network.
 * Nothing plays until the reader presses play, and a sentence saved without
 * audio is shown and said to be missing rather than skipped in silence.
 */
export function OfflineLibrary() {
  const { say } = useAnnouncer();
  const [saved, setSaved] = useState<SavedChapter[] | null>(null);
  const [estimate, setEstimate] = useState<{ usage: number; quota: number } | null>(null);
  const [open, setOpen] = useState<SavedChapter | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  /**
   * Where focus goes once the list is back on screen: the Listen button of
   * the chapter just left, or the page heading after a removal. Both moves
   * replace the element that had focus, which otherwise drops it to <body>.
   */
  const focusAfter = useRef<string | null>(null);

  useEffect(() => {
    const target = focusAfter.current;
    if (open || !target) return;
    focusAfter.current = null;
    const listen = document.querySelector<HTMLButtonElement>(
      `[data-listen="${CSS.escape(target)}"]`,
    );
    (listen ?? heading.current)?.focus();
  }, [open, saved]);

  const load = useCallback(async () => {
    setSaved(await listSaved().catch(() => []));
    try {
      const found = await navigator.storage?.estimate?.();
      if (found?.quota) setEstimate({ usage: found.usage ?? 0, quota: found.quota });
    } catch {
      // No estimate is not a problem worth reporting.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const found = await listSaved().catch(() => []);
      if (!cancelled) setSaved(found);
      try {
        const space = await navigator.storage?.estimate?.();
        if (!cancelled && space?.quota) {
          setEstimate({ usage: space.usage ?? 0, quota: space.quota });
        }
      } catch {
        // As above.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function remove(entry: SavedChapter) {
    await removeSaved(entry);
    focusAfter.current = "heading";
    say(strings.offlineRemoved(entry.chapter ?? entry.title));
    await load();
  }

  if (open) {
    return (
      <OfflinePlayer
        entry={open}
        onBack={() => {
          focusAfter.current = open.key;
          setOpen(null);
        }}
      />
    );
  }

  return (
    <div className="account-page">
      <h1 ref={heading} tabIndex={-1}>
        {strings.offlineHeading}
      </h1>
      <p className="hint">{strings.offlineHow}</p>
      {!offlineSupported() ? <p>{strings.offlineUnsupported}</p> : null}
      {estimate ? (
        <p>{strings.offlineSpace(megabytes(estimate.usage), megabytes(estimate.quota))}</p>
      ) : null}
      {saved === null ? null : saved.length === 0 ? (
        <p>{strings.offlineNothing}</p>
      ) : (
        <ul className="class-list">
          {saved.map((entry) => {
            const name = entry.chapter ?? strings.progressWholeBook;
            const missing = entry.clips.filter((c) => !c.url).length;
            return (
              <li key={entry.key} className="class-item">
                <h2>
                  {entry.title} — {name}
                </h2>
                <p>
                  {strings.offlineSize(entry.clips.length, megabytes(entry.bytes))}
                  {missing ? ` ${strings.offlineMissing(missing)}` : ""}
                </p>
                <div className="notice-actions">
                  {/* The book is in the name as well as the chapter: two
                      saved books both called "whole book" were two identical
                      buttons to a screen reader. */}
                  <button
                    className="btn btn-primary btn-sm"
                    type="button"
                    data-listen={entry.key}
                    onClick={() => setOpen(entry)}
                  >
                    {strings.offlineListen}
                    <span className="visually-hidden">
                      {" "}
                      — {entry.title} — {name}
                    </span>
                  </button>
                  <button className="btn btn-sm" type="button" onClick={() => void remove(entry)}>
                    {strings.offlineRemove}
                    <span className="visually-hidden">
                      {" "}
                      — {entry.title} — {name}
                    </span>
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <p>
        <Link href="/library">{strings.backToLibrary}</Link>
      </p>
    </div>
  );
}

function OfflinePlayer({ entry, onBack }: { entry: SavedChapter; onBack: () => void }) {
  const audio = useRef<HTMLAudioElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [index, setIndex] = useState<number | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    heading.current?.focus();
  }, []);

  // Each clip's object URL is released once the next replaces it.
  useEffect(
    () => () => {
      if (src) URL.revokeObjectURL(src);
    },
    [src],
  );

  async function playAt(start: number): Promise<void> {
    // The next sentence that has audio; missing ones are marked in the list.
    let at = start;
    while (at < entry.clips.length && !entry.clips[at]!.url) at += 1;
    if (at >= entry.clips.length) {
      setPlaying(false);
      return;
    }
    const blob = await savedClip(entry.clips[at]!.url!);
    if (!blob) return playAt(at + 1);
    setIndex(at);
    setSrc(URL.createObjectURL(blob));
  }

  function toggle() {
    if (playing) audio.current?.pause();
    else if (src) void audio.current?.play().catch(() => setPlaying(false));
    else void playAt(0);
  }

  const name = entry.chapter ?? strings.progressWholeBook;
  return (
    <div className="account-page">
      <p>
        <button className="btn btn-quiet btn-sm" type="button" onClick={onBack}>
          {strings.offlineBack}
        </button>
      </p>
      <h1 ref={heading} tabIndex={-1}>
        {entry.title} — {name}
      </h1>
      {/* Only ever given a source by a press, so nothing plays on arrival. */}
      {/* eslint-disable-next-line jsx-a11y/media-has-caption -- the words being spoken are the sentence list below, as text; a caption track would repeat them. */}
      <audio
        ref={audio}
        src={src ?? undefined}
        autoPlay
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => void playAt((index ?? 0) + 1)}
      />
      <div className="notice-actions">
        <button
          className="btn btn-sm"
          type="button"
          disabled={index === null || index === 0}
          onClick={() => void playAt(Math.max(0, (index ?? 0) - 1))}
        >
          {strings.previousSentence}
        </button>
        <button className="btn btn-primary btn-sm" type="button" onClick={toggle}>
          {playing ? strings.pause : strings.play}
        </button>
        <button
          className="btn btn-sm"
          type="button"
          disabled={index === null || index >= entry.clips.length - 1}
          onClick={() => void playAt((index ?? 0) + 1)}
        >
          {strings.nextSentence}
        </button>
      </div>
      <ol>
        {entry.clips.map((clip, position) => (
          <li key={clip.segment_id}>
            {clip.url ? (
              <button
                className="btn btn-quiet"
                type="button"
                lang="si"
                aria-current={position === index ? "true" : undefined}
                onClick={() => void playAt(position)}
              >
                {clip.text}
              </button>
            ) : (
              <p lang="si">
                {clip.text} <span className="hint">({strings.offlineNoAudio})</span>
              </p>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}
