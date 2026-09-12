"use client";

import { useEffect, useRef, useState } from "react";

import { usePreferences } from "@/components/PreferencesProvider";
import { roleLabel } from "@/lib/roles";
import { strings } from "@/lib/strings";
import type { Page, Segment } from "@/lib/types";

/**
 * The extracted Sinhala, as text.
 *
 * ## Every sentence is a button whose name is the sentence
 *
 * Navigating by button is the fastest way through a page in NVDA and TalkBack,
 * and this way that one stop reads the sentence *and* offers to play it. The
 * alternative — a small play icon beside each line — produces a list of forty
 * identically named buttons and a screen-reader user who has to leave the list
 * to find out what any of them say.
 *
 * ## Following the narration, without stealing the cursor
 *
 * While playing, the current sentence is scrolled into view, because a
 * low-vision reader at 300% zoom cannot see a highlight that is off screen. It
 * is never focused: moving focus every sentence would drag a screen-reader
 * cursor along with it and make the page impossible to read at your own pace.
 *
 * And following stops the moment the reader scrolls away themselves. Fighting
 * somebody who is looking at a different paragraph is worse than losing the
 * position, so when that happens a "return to the current sentence" button
 * appears and the panel stays where they put it.
 *
 * The workspace keys this component by page, so a page turn is a fresh mount:
 * new scroll position, and following switched back on.
 *
 * ## Highlighting is not only colour
 *
 * 1.4.1 says colour must not be the only means of conveying information. The
 * current sentence gets a wash, a solid left bar, and `aria-current`, so it is
 * identifiable to somebody who cannot distinguish the wash from the paper.
 */
export function ReadingPanel({
  page,
  segments,
  loading,
  currentId,
  playing,
  onPlayIndex,
  documentNotes,
}: {
  page: Page | null;
  segments: Segment[];
  loading: boolean;
  currentId: string | null;
  playing: boolean;
  onPlayIndex: (index: number) => void;
  documentNotes: string[];
}) {
  const { preferences } = usePreferences();
  const scroller = useRef<HTMLDivElement>(null);
  const [followingLost, setFollowingLost] = useState(false);
  /** Set while we are the ones scrolling, so our own scroll is not "the reader". */
  const selfScrolling = useRef(0);

  const scrollToCurrent = (smooth: boolean) => {
    const element = scroller.current?.querySelector<HTMLElement>('[data-current="true"]');
    if (!element) return;
    selfScrolling.current = Date.now();
    element.scrollIntoView({ block: "center", behavior: smooth ? "smooth" : "auto" });
    setFollowingLost(false);
  };

  useEffect(() => {
    if (!preferences.followSentence || !playing || !currentId || followingLost) return;
    const reduced =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const element = scroller.current?.querySelector<HTMLElement>('[data-current="true"]');
    if (!element) return;
    selfScrolling.current = Date.now();
    element.scrollIntoView({ block: "center", behavior: reduced ? "auto" : "smooth" });
  }, [preferences.followSentence, playing, currentId, followingLost]);

  useEffect(() => {
    const box = scroller.current;
    if (!box) return;
    const onScroll = () => {
      // A scroll within a moment of our own is ours, not theirs. Smooth
      // scrolling fires events for a while after it is asked for, and treating
      // those as the reader taking over would switch following off instantly.
      if (Date.now() - selfScrolling.current < 700) return;
      if (playing && preferences.followSentence) setFollowingLost(true);
    };
    box.addEventListener("scroll", onScroll, { passive: true });
    return () => box.removeEventListener("scroll", onScroll);
  }, [playing, preferences.followSentence]);

  return (
    <section className="panel reading-panel" aria-label={strings.readingPanel}>
      <div className="panel-bar">
        <h2 className="panel-title">{strings.readingPanel}</h2>
        <p className="hint">
          {page ? strings.sentenceCount(segments.length) : null}
          {page?.page_label ? ` · ${strings.printedPage} ${page.page_label}` : null}
        </p>
      </div>

      <div
        className="reading-body"
        ref={scroller}
        style={{ "--scale": preferences.textScale } as React.CSSProperties}
      >
        {documentNotes.length > 0 ? (
          <div className="notice notice-warn">
            <h3>{strings.documentNotesHeading}</h3>
            <ul>
              {documentNotes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {page ? <PageNotes page={page} /> : null}

        {loading ? (
          <p className="hint" aria-busy="true">
            {strings.pageLoading}
          </p>
        ) : segments.length === 0 ? (
          <p className="notice notice-warn">{strings.noSentences}</p>
        ) : (
          <ol className="sentences">
            {segments.map((segment, index) => {
              const current = currentId === segment.segment_id;
              const label = roleLabel(segment);
              return (
                <li
                  key={segment.segment_id}
                  className="sentence"
                  data-current={current}
                  data-role={segment.role}
                  data-level={segment.level ?? undefined}
                >
                  <button
                    type="button"
                    className="sentence-text"
                    aria-current={current ? "true" : undefined}
                    onClick={() => onPlayIndex(index)}
                  >
                    {/*
                     * The role is part of the accessible name, not a visual
                     * badge alone. A sighted reader sees a caption is a caption
                     * from its position; somebody listening has only what is
                     * announced, and a caption read in sequence with the
                     * paragraph beside it is the defect this exists to fix.
                     */}
                    {label ? <span className="sentence-role">{label}</span> : null}
                    {segment.display_text}
                  </button>
                </li>
              );
            })}
          </ol>
        )}
      </div>

      {followingLost ? (
        <div className="return-to-sentence">
          <button type="button" className="btn btn-sm" onClick={() => scrollToCurrent(true)}>
            {strings.returnToSentence}
          </button>
        </div>
      ) : null}
    </section>
  );
}

/**
 * What this page loses, in the page rather than behind a warning icon.
 *
 * CLAUDE.md forbids claiming full accessibility when content has not been
 * handled. This is where that promise is kept or broken.
 */
function PageNotes({ page }: { page: Page }) {
  const messages: string[] = [];
  if (page.quality === "undecodable") messages.push(strings.qualityUndecodable);
  else if (page.quality === "needs_review") messages.push(strings.qualityNeedsReview);
  if (page.kind === "image") messages.push(strings.kindImage);
  for (const note of page.notes) messages.push(note);

  if (messages.length === 0) return null;
  return (
    <div className="notice notice-warn">
      <h3>{strings.pageNotesHeading}</h3>
      <ul>
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </div>
  );
}
