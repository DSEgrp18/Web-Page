"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

/**
 * The two things this interface is allowed to say out loud, and the rules for
 * when it may say them.
 *
 * **Polite** is for progress and confirmation: a book finished preparing, a
 * page loaded, playback paused. It waits for the screen reader to finish what
 * it is already saying.
 *
 * **Assertive** is for errors alone. It interrupts. CLAUDE.md reserves it for
 * urgent errors, and that restraint is the whole value: a live region that
 * interrupts constantly is one a reader turns off.
 *
 * What is deliberately *not* announced: each sentence during continuous
 * narration. The reader is listening to the book; a screen reader talking over
 * every sentence boundary competes with the very thing they asked for. Sentence
 * position is announced when the reader *asks* for it by pressing a control.
 */

interface AnnouncerValue {
  /** Progress and confirmation. Waits its turn. */
  say: (message: string) => void;
  /** Errors only. Interrupts. */
  alert: (message: string) => void;
}

const AnnouncerContext = createContext<AnnouncerValue>({
  say: () => {},
  alert: () => {},
});

export function useAnnouncer(): AnnouncerValue {
  return useContext(AnnouncerContext);
}

interface Announcement {
  text: string;
  /** Bumped on every call so repeating the same message still announces it. */
  seq: number;
}

const EMPTY: Announcement = { text: "", seq: 0 };

/**
 * How long a message stays in the DOM after being announced.
 *
 * It has to be cleared. A live region is part of the accessibility tree, so a
 * message left in one is read *again* by anyone browsing the page afterwards —
 * and errors are also shown on the page, so the reader would meet the same
 * sentence twice with no explanation. Screen readers capture the text when it
 * changes, not when they get around to speaking it, so removing it a few
 * seconds later does not truncate anything.
 */
const CLEAR_AFTER_MS = 4000;

function useAnnouncementSlot(): [Announcement, (message: string) => void] {
  const [announcement, setAnnouncement] = useState<Announcement>(EMPTY);

  const announce = useCallback((message: string) => {
    setAnnouncement((previous) => ({ text: message, seq: previous.seq + 1 }));
  }, []);

  useEffect(() => {
    if (!announcement.text) return;
    const timer = setTimeout(() => {
      // Only clear the message this effect was started for; a newer one that
      // arrived in the meantime keeps its own full time.
      setAnnouncement((current) =>
        current.seq === announcement.seq ? { text: "", seq: current.seq } : current,
      );
    }, CLEAR_AFTER_MS);
    return () => clearTimeout(timer);
  }, [announcement]);

  return [announcement, announce];
}

export function AnnouncerProvider({ children }: { children: ReactNode }) {
  const [polite, say] = useAnnouncementSlot();
  const [assertive, alert] = useAnnouncementSlot();

  const value = useMemo(() => ({ say, alert }), [say, alert]);

  return (
    <AnnouncerContext.Provider value={value}>
      {children}
      {/*
        The message is keyed by a sequence number so that saying the same thing
        twice replaces the child node. Screen readers announce a live region
        when its contents *change*; identical text is not a change, and the
        second "පිටුව ලබා ගනිමින්…" would be silent without this.
      */}
      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        <span key={polite.seq}>{polite.text}</span>
      </div>
      <div className="visually-hidden" role="alert" aria-live="assertive" aria-atomic="true">
        <span key={assertive.seq}>{assertive.text}</span>
      </div>
    </AnnouncerContext.Provider>
  );
}
