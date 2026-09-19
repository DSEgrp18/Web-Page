"use client";

import { useEffect, useId, useRef } from "react";

import { strings } from "@/lib/strings";
import type { Chapter } from "@/lib/types";

/**
 * The book's chapters, as a sheet: අන්තර්ගතය.
 *
 * ## A sheet at every width, not a third column
 *
 * The design draws a permanent left panel. The workspace it was drawn for had
 * one reading column; this one has the printed page and the words side by
 * side, and a third column would squeeze both of them to make room for a list
 * a reader needs for five seconds. So it is a native modal `<dialog>` at every
 * width, which is what the design asks for at 390 px anyway: `showModal()`
 * traps focus, Escape closes it, and focus goes back to the button that opened
 * it.
 *
 * ## Choosing a chapter moves; it never plays
 *
 * CLAUDE.md forbids narration starting by itself. The chapter's first page
 * opens and focus lands on the page heading, exactly as "next page" does, so
 * the reader hears where they are and presses play themselves.
 *
 * ## "None" and "not known" are different sentences
 *
 * `[]` means the book was examined and its type gives no chapters. `null` means
 * nobody looked, because the book was prepared before chapters were detected.
 * Saying "this book has no chapters" about the second would be false.
 *
 * Mounted only while open, like the rename dialog, so there is no stale state.
 */
export function ContentsSheet({
  chapters,
  current,
  onChoose,
  onClose,
}: {
  chapters: Chapter[] | null;
  /** Index into `chapters` of the chapter holding the current page, or -1. */
  current: number;
  onChoose: (chapter: Chapter) => void;
  /** Escape, the close button, or a click on the backdrop. */
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const list = useRef<HTMLOListElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const headingId = useId();

  /**
   * Leave the top layer before anything else happens. While a modal dialog is
   * open the rest of the page is inert, so focusing the page heading or the
   * contents button from inside it silently does nothing.
   */
  const leave = (then: () => void) => {
    if (dialog.current?.open) dialog.current.close();
    then();
  };

  useEffect(() => {
    dialog.current?.showModal();
    // Start on the chapter the reader is in, so "where am I" is the first
    // thing heard and the next chapter is one Tab away.
    const buttons = list.current?.querySelectorAll<HTMLButtonElement>("button");
    const target = buttons?.[Math.max(current, 0)] ?? closeButton.current;
    target?.focus();
  }, [current]);

  return (
    /* The backdrop click is a pointer affordance on an element that is already
       a dialog; Escape is handled by onCancel. See RenameDialog. */
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={dialog}
      className="dialog contents-sheet"
      aria-labelledby={headingId}
      onCancel={(event) => {
        event.preventDefault();
        leave(onClose);
      }}
      onClick={(event) => {
        if (event.target === dialog.current) leave(onClose);
      }}
    >
      <div className="dialog-body">
        <div className="contents-head">
          <h2 id={headingId}>{strings.contentsHeading}</h2>
          <button
            ref={closeButton}
            type="button"
            className="btn btn-quiet btn-sm"
            onClick={() => leave(onClose)}
          >
            {strings.closePanel}
          </button>
        </div>

        {chapters === null ? (
          <p>{strings.contentsUnknown}</p>
        ) : chapters.length === 0 ? (
          <p>{strings.contentsNone}</p>
        ) : (
          <nav aria-labelledby={headingId}>
            <ol ref={list} className="contents-list">
              {chapters.map((chapter, index) => (
                <li key={`${chapter.page_index}-${index}`}>
                  <button
                    type="button"
                    className="contents-row"
                    aria-current={index === current ? "true" : undefined}
                    onClick={() => leave(() => onChoose(chapter))}
                  >
                    {chapter.number ? (
                      <span className="contents-number latin">{chapter.number}</span>
                    ) : null}
                    <span className="contents-title">
                      {chapter.title || `${strings.chapterWord} ${chapter.number ?? index + 1}`}
                    </span>
                    <span className="contents-page hint">
                      {strings.pageWord} {chapter.page_index + 1}
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>
        )}
      </div>
    </dialog>
  );
}

/** The chapter the page is in: the last one opening at or before it, or -1. */
export function chapterAt(chapters: Chapter[] | null, pageIndex: number): number {
  if (!chapters) return -1;
  let found = -1;
  chapters.forEach((chapter, index) => {
    if (chapter.page_index <= pageIndex) found = index;
  });
  return found;
}
