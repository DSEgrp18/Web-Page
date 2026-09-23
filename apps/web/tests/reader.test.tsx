import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Reader } from "../src/components/Reader";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage, type FakeBook } from "./fakeApi";
import { noticeText, politeText, renderApp } from "./render";
import { playCalls, playedElements, scrollIntoViewCalls, setCurrentTime } from "./setup";

const FIRST = "පළමු වාක්‍යය.";
const SECOND = "දෙවන වාක්‍යය.";
const ON_PAGE_TWO = "දෙවන පිටුවේ වාක්‍යය.";

function book(overrides: Partial<FakeBook> = {}): FakeBook {
  return {
    document_id: "doc-1",
    filename: "ඉතිහාසය.pdf",
    version: "v1",
    pages: [readablePage(0, [FIRST, SECOND]), readablePage(1, [ON_PAGE_TWO], "13")],
    ...overrides,
  };
}

function openReader(server: FakeServer) {
  return renderApp(<Reader documentId="doc-1" />, server);
}

describe("the tab title", () => {
  it("names the book once it has loaded", async () => {
    openReader(new FakeServer({ books: [book()] }));

    // The title is set in an effect after the book arrives, which can land
    // a tick after the page's sentences render, so wait for it.
    await waitFor(() => expect(document.title).toBe(`ඉතිහාසය.pdf — ${strings.appName}`));
  });

  it("uses the name the reader gave the book, not its filename", async () => {
    openReader(new FakeServer({ books: [book({ title: "ඉතිහාසය 11 ශ්‍රේණිය" })] }));

    // The title is set in an effect after the book arrives, which can land
    // a tick after the page's sentences render, so wait for it.
    await waitFor(() => expect(document.title).toBe(`ඉතිහාසය 11 ශ්‍රේණිය — ${strings.appName}`));
  });
});

/**
 * The reading panel's own pager.
 *
 * Both panels carry a "next page" control now, so an unqualified query for one
 * matches two elements. Scoping to the reading side keeps these tests about the
 * text rather than about the PDF canvas, which jsdom cannot render anyway.
 */
function readingPager() {
  const pager = document.querySelector<HTMLElement>(".reading-pager");
  if (!pager) throw new Error("the reading panel has no pager");
  return within(pager);
}

describe("arriving at a page", () => {
  it("plays nothing until a person asks", async () => {
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await screen.findByRole("button", { name: FIRST });
    // CLAUDE.md forbids narration on page load. A page that starts talking
    // talks over the screen reader announcing it.
    expect(playCalls).toHaveLength(0);
    expect(server.callsTo("GET", /\/audio$/)).toHaveLength(0);
  });

  it("offers every sentence as a control whose name is the sentence", async () => {
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    expect(await screen.findByRole("button", { name: FIRST })).toBeTruthy();
    expect(screen.getByRole("button", { name: SECOND })).toBeTruthy();
  });

  it("shows word boundaries for the selected sentence without starting audio", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    const toggle = await screen.findByRole("button", { name: strings.showWords });
    await user.click(toggle);
    const panel = screen.getByRole("region", { name: strings.sentenceWords });
    expect(
      within(panel)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["පළමු", "වාක්‍යය"]);
    expect(playCalls).toHaveLength(0);

    await user.click(screen.getByRole("button", { name: SECOND }));
    await waitFor(() => expect(panel.textContent).toContain(SECOND));
    expect(
      within(panel)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["දෙවන", "වාක්‍යය"]);
  });

  it("points the word toggle at the panel only while the panel is there", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    const toggle = await screen.findByRole("button", { name: strings.showWords });

    // aria-controls naming an element that does not exist is invalid ARIA, and
    // a closed disclosure has no element to name.
    expect(toggle.getAttribute("aria-controls")).toBeNull();
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await user.click(toggle);
    const panel = screen.getByRole("region", { name: strings.sentenceWords });
    const controls = screen
      .getByRole("button", { name: strings.hideWords })
      .getAttribute("aria-controls");

    expect(controls).toBeTruthy();
    expect(controls).toBe(panel.id);
    // Generated rather than fixed, so two readers on one screen cannot collide.
    expect(panel.id).not.toBe("sentence-words");
  });

  it("announces the page politely, with how much is on it", async () => {
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await screen.findByRole("button", { name: FIRST });
    await waitFor(() => expect(politeText()).toContain(strings.sentenceCount(2)));
  });

  it("shows the printed page number, not only the file position", async () => {
    const server = new FakeServer({ books: [book()] });
    openReader(server);
    // Page 0 of the file is printed "12". A reader following along with a
    // sighted classmate needs the number on the paper, so it is stated beside
    // the text rather than left to the file position.
    await waitFor(() => {
      // The label is assembled from several nodes, so this reads the bar it
      // sits in rather than hunting for one element containing all of it.
      const bar = document.querySelector(".reading-panel .panel-bar");
      expect(bar?.textContent).toContain(strings.printedPage);
      expect(bar?.textContent).toContain("12");
    });
  });
});

describe("listening", () => {
  it("plays the sentence the reader chose, and marks it as current", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: SECOND }));

    await waitFor(() => expect(playCalls).toHaveLength(1));
    const chosen = screen.getByRole("button", { name: SECOND });
    expect(chosen.getAttribute("aria-current")).toBe("true");
    expect(screen.getByRole("button", { name: FIRST }).getAttribute("aria-current")).toBeNull();
  });

  it("continues to the next sentence without narrating that it did", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: FIRST }));
    await waitFor(() => expect(playCalls).toHaveLength(1));
    const politeBefore = politeText();

    // What a browser does at the end of a clip.
    await act(async () => {
      playedElements[0]?.dispatchEvent(new Event("ended"));
    });

    await waitFor(() => expect(playCalls).toHaveLength(2));
    expect(screen.getByRole("button", { name: SECOND }).getAttribute("aria-current")).toBe("true");
    // The reader is listening to the book. A screen reader naming every
    // sentence boundary would talk over the thing they asked for.
    expect(politeText()).toBe(politeBefore);
  });

  it("saves where the reader stopped when they pause", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: FIRST }));
    await waitFor(() => expect(playCalls).toHaveLength(1));

    setCurrentTime(7.5);
    await user.click(screen.getByRole("button", { name: strings.pause }));

    await waitFor(() => expect(server.callsTo("PUT", /\/progress$/)).toHaveLength(1));
    expect(server.progress).toMatchObject({ segment_id: "0000-s0", offset_seconds: 7.5 });
  });

  it("stopping leaves no sentence marked as being read", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: FIRST }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: FIRST }).getAttribute("aria-current")).toBe("true"),
    );

    await user.click(screen.getByRole("button", { name: strings.stop }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: FIRST }).getAttribute("aria-current")).toBeNull(),
    );
  });

  it("asks for each clip once, however many times it is played", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    const sentence = await screen.findByRole("button", { name: FIRST });
    await user.click(sentence);
    await waitFor(() => expect(playCalls).toHaveLength(1));
    await user.click(sentence);
    await waitFor(() => expect(playCalls).toHaveLength(2));

    // The second press replays what was already fetched. On a real deployment
    // the alternative is a second GPU job for audio already in hand.
    expect(server.callsTo("GET", /segments\/0000-s0\/audio$/)).toHaveLength(1);
  });

  it("scrolls the current sentence into view while playing, without moving focus", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    const first = await screen.findByRole("button", { name: FIRST });
    first.focus();
    expect(document.activeElement).toBe(first);

    scrollIntoViewCalls.length = 0;
    await user.click(first);
    await waitFor(() => expect(playCalls).toHaveLength(1));
    await waitFor(() => expect(scrollIntoViewCalls.length).toBeGreaterThan(0));
    expect(scrollIntoViewCalls.at(-1)).toMatchObject({ block: "center", behavior: "smooth" });
    expect(document.activeElement).toBe(first);

    const beforeAdvance = scrollIntoViewCalls.length;
    await act(async () => {
      playedElements[0]?.dispatchEvent(new Event("ended"));
    });
    await waitFor(() => expect(playCalls).toHaveLength(2));
    await waitFor(() => expect(scrollIntoViewCalls.length).toBeGreaterThan(beforeAdvance));
    expect(document.activeElement).toBe(first);
  });

  it("jumps instantly when reduced motion is preferred", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as typeof window.matchMedia;

    try {
      openReader(server);
      scrollIntoViewCalls.length = 0;
      await user.click(await screen.findByRole("button", { name: FIRST }));
      await waitFor(() =>
        expect(scrollIntoViewCalls.some((call) => call.behavior === "auto")).toBe(true),
      );
    } finally {
      window.matchMedia = originalMatchMedia;
    }
  });

  it("does not scroll while paused", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: FIRST }));
    await waitFor(() => expect(playCalls).toHaveLength(1));
    await user.click(screen.getByRole("button", { name: strings.pause }));
    const afterPause = scrollIntoViewCalls.length;

    // Still on the same sentence, now paused: follow-reading must stay quiet.
    await act(async () => {
      await Promise.resolve();
    });
    expect(scrollIntoViewCalls.length).toBe(afterPause);
  });
});

describe("coming back", () => {
  it("offers to resume, and does not resume by itself", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [book()],
      progress: {
        document_id: "doc-1",
        segment_id: "0000-s1",
        offset_seconds: 3.25,
        document_version: "v1",
        updated_at: "2026-09-09T00:00:00Z",
        segment_index: 0,
        stale: false,
      },
    });
    openReader(server);

    const resume = await screen.findByRole("button", { name: strings.resume });
    expect(playCalls).toHaveLength(0);

    await user.click(resume);
    await waitFor(() => expect(playCalls).toHaveLength(1));
    await waitFor(() => expect(playedElements[0]?.currentTime).toBe(3.25));
  });

  it("warns when the book was reprocessed after the position was saved", async () => {
    const server = new FakeServer({
      books: [book()],
      progress: {
        document_id: "doc-1",
        segment_id: "0000-s1",
        offset_seconds: 3.25,
        document_version: "v0",
        updated_at: "2026-09-09T00:00:00Z",
        segment_index: 0,
        stale: true,
      },
    });
    openReader(server);

    expect(await screen.findByText(strings.resumeStale)).toBeTruthy();
  });

  it("opens the page the reader was on, not the first one", async () => {
    const server = new FakeServer({
      books: [book()],
      progress: {
        document_id: "doc-1",
        segment_id: "0001-s0",
        offset_seconds: 1,
        document_version: "v1",
        updated_at: "2026-09-09T00:00:00Z",
        segment_index: 0,
        stale: false,
      },
    });
    openReader(server);

    expect(await screen.findByRole("button", { name: ON_PAGE_TWO })).toBeTruthy();
  });
});

describe("bookmarking", () => {
  it("saves the playing sentence and offers a reversible undo", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: FIRST }));
    const bookmark = await screen.findByRole("button", { name: strings.bookmarkSentence(1, 1) });
    await user.click(bookmark);

    await waitFor(() => expect(server.bookmarks).toHaveLength(1));
    expect(await screen.findByRole("button", { name: strings.undoBookmark })).toBeTruthy();
    expect(politeText()).toContain(strings.bookmarkSaved);

    await user.click(screen.getByRole("button", { name: strings.undoBookmark }));
    await waitFor(() => expect(server.bookmarks).toEqual([]));
  });

  it("opens a bookmarked sentence without playing it", async () => {
    const server = new FakeServer({ books: [book()] });
    renderApp(<Reader documentId="doc-1" bookmarkSegmentId="0001-s0" />, server);

    const sentence = await screen.findByRole("button", { name: ON_PAGE_TWO });
    await waitFor(() => expect(sentence.getAttribute("aria-current")).toBe("true"));
    expect(playCalls).toHaveLength(0);
  });
});

describe("moving between pages", () => {
  it("moves focus to the heading so the change is noticed", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await screen.findByRole("button", { name: FIRST });
    await user.click(readingPager().getByRole("button", { name: strings.nextPage }));

    await screen.findByRole("button", { name: ON_PAGE_TWO });
    // Without this a screen reader stays where it was and reads nothing new;
    // the reader presses "next page" and hears silence.
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 })),
    );
  });

  it("does not steal focus on arrival", async () => {
    const server = new FakeServer({ books: [book()] });
    openReader(server);
    await screen.findByRole("button", { name: FIRST });
    expect(document.activeElement).toBe(document.body);
  });

  it("stops at the last page rather than asking for one that is not there", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await screen.findByRole("button", { name: FIRST });
    await user.click(readingPager().getByRole("button", { name: strings.nextPage }));
    await screen.findByRole("button", { name: ON_PAGE_TWO });

    expect(
      readingPager().getByRole("button", { name: strings.nextPage }).hasAttribute("disabled"),
    ).toBe(true);
    expect(server.callsTo("GET", /\/pages\/2$/)).toHaveLength(0);
  });
});

const CHAPTERS = [
  { title: "කාර්මික විප්ලවය", number: "01", page_index: 0 },
  { title: "ජාතික පුනරුදය", number: "02", page_index: 1 },
];

function contentsSheet() {
  return within(screen.getByRole("dialog", { name: strings.contentsHeading }));
}

describe("moving between chapters", () => {
  it("lists the chapters in a named navigation region, marking the current one", async () => {
    const user = userEvent.setup();
    openReader(new FakeServer({ books: [book({ chapters: CHAPTERS })] }));
    await screen.findByRole("button", { name: FIRST });

    await user.click(screen.getByRole("button", { name: strings.contentsOpen }));

    const sheet = contentsSheet();
    expect(sheet.getByRole("navigation", { name: strings.contentsHeading })).toBeTruthy();
    const rows = sheet.getAllByRole("button", { name: /පිටුව/ });
    expect(rows).toHaveLength(2);
    // Current is announced, not only coloured.
    expect(rows[0]?.getAttribute("aria-current")).toBe("true");
    expect(rows[1]?.getAttribute("aria-current")).toBeNull();
    // It opens on the chapter the reader is in.
    expect(document.activeElement).toBe(rows[0]);
  });

  it("opens a chapter's first page and moves focus to the heading, without playing", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book({ chapters: CHAPTERS })] });
    openReader(server);
    await screen.findByRole("button", { name: FIRST });

    await user.click(screen.getByRole("button", { name: strings.contentsOpen }));
    await user.click(contentsSheet().getByRole("button", { name: /ජාතික පුනරුදය/ }));

    await screen.findByRole("button", { name: ON_PAGE_TWO });
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("heading", { level: 1 })),
    );
    // Rule 1: nothing speaks unless a person asks.
    expect(playCalls).toHaveLength(0);
    expect(server.callsTo("GET", /\/audio$/)).toHaveLength(0);
    // The header says which chapter this is, as the design shows it.
    expect(screen.getByText("02 / ජාතික පුනරුදය")).toBeTruthy();
  });

  it("closes on Escape and gives focus back to the button that opened it", async () => {
    const user = userEvent.setup();
    openReader(new FakeServer({ books: [book({ chapters: CHAPTERS })] }));
    await screen.findByRole("button", { name: FIRST });
    const opener = screen.getByRole("button", { name: strings.contentsOpen });

    await user.click(opener);
    // jsdom does not turn Escape into the dialog's cancel event the way a
    // browser does, so fire the event the platform would. See library tests.
    await act(async () => {
      document
        .querySelector("dialog[open]")
        ?.dispatchEvent(new Event("cancel", { cancelable: true }));
    });

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("says in words when the book has no chapters", async () => {
    const user = userEvent.setup();
    openReader(new FakeServer({ books: [book({ chapters: [] })] }));
    await screen.findByRole("button", { name: FIRST });

    await user.click(screen.getByRole("button", { name: strings.contentsOpen }));

    expect(contentsSheet().getByText(strings.contentsNone)).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: strings.contentsHeading })).toBeNull();
  });

  it("does not claim a book has no chapters when nobody looked", async () => {
    const user = userEvent.setup();
    openReader(new FakeServer({ books: [book({ chapters: null })] }));
    await screen.findByRole("button", { name: FIRST });

    await user.click(screen.getByRole("button", { name: strings.contentsOpen }));

    expect(contentsSheet().getByText(strings.contentsUnknown)).toBeTruthy();
    expect(contentsSheet().queryByText(strings.contentsNone)).toBeNull();
  });
});

describe("telling the reader what they are missing", () => {
  it("says a page could not be read", async () => {
    const unreadable = readablePage(0, []);
    unreadable.quality = "undecodable";
    unreadable.kind = "image";
    unreadable.notes = ["මෙම පිටුවේ අකුරු පැරණි ෆොන්ටයකින් ඇත."];

    const server = new FakeServer({ books: [book({ pages: [unreadable] })] });
    openReader(server);

    expect(await screen.findByText(strings.qualityUndecodable)).toBeTruthy();
    expect(screen.getByText(strings.kindImage)).toBeTruthy();
    // The server's own note is shown as written, not paraphrased.
    expect(screen.getByText(unreadable.notes[0]!)).toBeTruthy();
    expect(screen.getByText(strings.noSentences)).toBeTruthy();
  });

  it("says out loud that placeholder audio is not speech", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()], realModel: false });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: FIRST }));

    // Shown on the page and announced. A listener cannot tell a tone from
    // speech they were not expecting.
    expect(await screen.findByText(strings.placeholderAudioHeading)).toBeTruthy();
    await waitFor(() => expect(politeText()).toBe(strings.placeholderAudio));
  });

  it("does not cry placeholder when the model is real", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()], realModel: true });
    openReader(server);

    await user.click(await screen.findByRole("button", { name: FIRST }));
    await waitFor(() => expect(playCalls).toHaveLength(1));
    expect(screen.queryByText(strings.placeholderAudioHeading)).toBeNull();
  });

  it("says a book was not found rather than guessing why", async () => {
    const server = new FakeServer({ books: [] });
    openReader(server);
    // The API answers 404 for a book that does not exist and for one belonging
    // to someone else. The interface must not invent the difference.
    await waitFor(() => expect(noticeText()).toContain(strings.errorNotFound));
  });
});
