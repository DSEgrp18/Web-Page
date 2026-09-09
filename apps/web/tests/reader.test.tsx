import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Reader } from "../src/components/Reader";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage, type FakeBook } from "./fakeApi";
import { noticeText, politeText, renderApp } from "./render";
import { playCalls, playedElements, setCurrentTime } from "./setup";

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
    // sighted classmate needs the number on the paper.
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 }).textContent).toContain("12"),
    );
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
        stale: false,
      },
    });
    openReader(server);

    expect(await screen.findByRole("button", { name: ON_PAGE_TWO })).toBeTruthy();
  });
});

describe("moving between pages", () => {
  it("moves focus to the heading so the change is noticed", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    openReader(server);

    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: strings.nextPage }));

    await screen.findByRole("button", { name: ON_PAGE_TWO });
    // Without this a screen reader stays where it was and reads nothing new;
    // the reader presses "next page" and hears silence.
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2 })),
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
    await user.click(screen.getByRole("button", { name: strings.nextPage }));
    await screen.findByRole("button", { name: ON_PAGE_TWO });

    expect(screen.getByRole("button", { name: strings.nextPage }).hasAttribute("disabled")).toBe(
      true,
    );
    expect(server.callsTo("GET", /\/pages\/2$/)).toHaveLength(0);
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
