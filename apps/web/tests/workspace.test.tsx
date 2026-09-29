import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Reader } from "../src/components/Reader";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage, type FakeBook } from "./fakeApi";
import { politeText, renderApp } from "./render";
import { playCalls } from "./setup";

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

function open(server: FakeServer) {
  return renderApp(<Reader documentId="doc-1" />, server);
}

function divider() {
  return screen.getByRole("separator", { name: strings.splitLabel });
}

describe("the two panels", () => {
  it("names both panels so a screen reader can tell them apart", async () => {
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    expect(screen.getByRole("region", { name: strings.originalPanel })).toBeTruthy();
    expect(screen.getByRole("region", { name: strings.readingPanel })).toBeTruthy();
  });

  it("gives the divider a keyboard, not just a drag handle", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    const handle = divider();
    expect(handle.getAttribute("aria-valuenow")).toBe("50");

    handle.focus();
    await user.keyboard("{ArrowRight}");
    await waitFor(() => expect(divider().getAttribute("aria-valuenow")).toBe("55"));

    await user.keyboard("{Home}");
    await waitFor(() => expect(divider().getAttribute("aria-valuenow")).toBe("20"));

    // Enter is the way back to an even split without hunting for the middle.
    await user.keyboard("{Enter}");
    await waitFor(() => expect(divider().getAttribute("aria-valuenow")).toBe("50"));
  });

  it("never lets one panel squeeze the other out of existence", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    divider().focus();
    // Far past the limit in both directions.
    for (let press = 0; press < 20; press += 1) await user.keyboard("{ArrowLeft}");
    expect(Number(divider().getAttribute("aria-valuenow"))).toBeGreaterThanOrEqual(20);

    for (let press = 0; press < 40; press += 1) await user.keyboard("{ArrowRight}");
    expect(Number(divider().getAttribute("aria-valuenow"))).toBeLessThanOrEqual(80);
  });

  it("remembers the width the reader chose", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    const first = open(server);
    await screen.findByRole("button", { name: FIRST });

    divider().focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    await waitFor(() => expect(divider().getAttribute("aria-valuenow")).toBe("60"));

    first.unmount();
    open(server);
    await screen.findByRole("button", { name: FIRST });
    expect(divider().getAttribute("aria-valuenow")).toBe("60");
  });

  it("collapses to one panel and back", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    await user.click(screen.getByRole("button", { name: strings.expandReading }));
    // With one panel filling the width there is nothing to divide.
    expect(screen.queryByRole("separator", { name: strings.splitLabel })).toBeNull();
    expect(screen.getByRole("button", { name: FIRST })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: strings.restoreSplit }));
    expect(divider()).toBeTruthy();
  });

  it("leaves a bar where a collapsed panel was, which brings it back", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    await user.click(screen.getByRole("button", { name: strings.expandReading }));
    // Named for the panel it restores, not "both panels" a second time.
    const bar = screen.getByRole("button", { name: strings.restorePanel(strings.originalPanel) });
    await user.click(bar);

    expect(divider()).toBeTruthy();
    // The bar is gone with the press; focus is on what replaced it.
    expect(document.activeElement).toBe(divider());
  });

  it("returns to an even split on a double-click", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    divider().focus();
    await user.keyboard("{ArrowRight}{ArrowRight}");
    await waitFor(() => expect(divider().getAttribute("aria-valuenow")).toBe("60"));
    await user.dblClick(divider());
    await waitFor(() => expect(divider().getAttribute("aria-valuenow")).toBe("50"));
  });
});

describe("the phone tabs", () => {
  it("are one stop in the tab order, moved between with the arrow keys", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    const original = screen.getByRole("tab", { name: strings.originalPanel });
    const reading = screen.getByRole("tab", { name: strings.readingPanel });
    expect(reading.getAttribute("aria-selected")).toBe("true");
    expect(reading.tabIndex).toBe(0);
    expect(original.tabIndex).toBe(-1);

    reading.focus();
    await user.keyboard("{ArrowLeft}");
    expect(document.activeElement).toBe(original);
    expect(original.getAttribute("aria-selected")).toBe("true");
    expect(original.tabIndex).toBe(0);

    await user.keyboard("{End}");
    expect(document.activeElement).toBe(reading);
    expect(reading.getAttribute("aria-selected")).toBe("true");
  });
});

describe("keeping the panels in step", () => {
  it("says which state the sync toggle is in, rather than leaving it to an icon", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    const sync = screen.getByRole("button", { name: new RegExp(strings.syncPages) });
    expect(sync.getAttribute("aria-pressed")).toBe("true");

    await user.click(sync);
    const off = screen.getByRole("button", { name: new RegExp(strings.syncPagesOff) });
    expect(off.getAttribute("aria-pressed")).toBe("false");
  });

  it("moves the original page with the text while sync is on", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    const pager = within(document.querySelector<HTMLElement>(".reading-pager")!);
    await user.click(pager.getByRole("button", { name: strings.nextPage }));
    await screen.findByRole("button", { name: ON_PAGE_TWO });

    // The PDF side's page field follows, so the two halves are showing the
    // same page of the same book.
    const stepper = document.querySelector<HTMLInputElement>(".page-number");
    expect(stepper?.value).toBe("2");
  });

  it("lets the panels come apart when the reader asks", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    await user.click(screen.getByRole("button", { name: new RegExp(strings.syncPages) }));

    const pager = within(document.querySelector<HTMLElement>(".reading-pager")!);
    await user.click(pager.getByRole("button", { name: strings.nextPage }));
    await screen.findByRole("button", { name: ON_PAGE_TWO });

    // Text moved; the printed page did not. Comparing a figure on one page
    // with the text on another is a real reason to break the link.
    const stepper = document.querySelector<HTMLInputElement>(".page-number");
    expect(stepper?.value).toBe("1");
  });
});

describe("the assistant", () => {
  it("has an edge that sets its width from the keyboard, said and remembered", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    const first = open(server);
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    const edge = () => screen.getByRole("separator", { name: strings.assistantResize });
    expect(edge().getAttribute("aria-valuenow")).toBe("26");
    // Said as a share of the screen, not left for the eye to judge.
    expect(edge().getAttribute("aria-valuetext")).toMatch(/%/);

    edge().focus();
    // The edge is on the panel's left: moving it left widens the panel.
    await user.keyboard("{ArrowLeft}");
    await waitFor(() => expect(edge().getAttribute("aria-valuenow")).toBe("28"));
    await user.keyboard("{PageDown}");
    await waitFor(() => expect(edge().getAttribute("aria-valuenow")).toBe("22"));
    await user.keyboard("{Home}");
    await waitFor(() => expect(edge().getAttribute("aria-valuenow")).toBe("20"));
    await user.keyboard("{PageUp}");
    await waitFor(() => expect(edge().getAttribute("aria-valuenow")).toBe("26"));
    await user.keyboard("{End}");
    const widest = Number(edge().getAttribute("aria-valuenow"));
    expect(widest).toBeGreaterThan(26);
    expect(widest).toBeLessThanOrEqual(48);

    first.unmount();
    open(server);
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));
    expect(edge().getAttribute("aria-valuenow")).toBe(String(widest));
  });

  it("stays shut until it is asked for, and says which book it answers about", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    const toggle = screen.getByRole("button", { name: new RegExp(strings.assistantToggle) });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");

    await user.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    // Grounded in one document. An answer from the wrong book is the failure
    // this label exists to make visible.
    expect(screen.getByText(strings.assistantFor("ඉතිහාසය.pdf"))).toBeTruthy();
  });

  it("does not offer to summarise or explain, because it cannot", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    // The API's answerer is extractive: it returns the book's own sentences.
    // A "summarise this page" button would be a control for a capability that
    // does not exist, so the panel says what it actually does instead.
    expect(screen.getByText(strings.assistantExtractive)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /සාරාංශ/ })).toBeNull();
  });

  it("says the answer is the book's own words when it is", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    await user.type(screen.getByLabelText(strings.questionLabel), "පළමු");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));

    expect(await screen.findByText(strings.answerFromBook)).toBeTruthy();
    expect(screen.getByText(strings.assistantExtractive)).toBeTruthy();
    expect(screen.queryByText(strings.answerFromAi)).toBeNull();
  });

  it("says the answer was written by a model when it was", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()], generatedAnswers: true }));
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    await user.type(screen.getByLabelText(strings.questionLabel), "පළමු");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));

    // The whole point of the flag. A reader who cannot see the page has no
    // other way to tell whose words these are, and being told the book said
    // something a model wrote is the failure this prevents.
    expect(await screen.findByText(strings.answerFromAi)).toBeTruthy();
    expect(screen.getByText(strings.assistantGenerated)).toBeTruthy();
    expect(screen.queryByText(strings.assistantExtractive)).toBeNull();
  });

  it("makes the cautious claim before anything is asked, when the server writes answers", async () => {
    // It used to say "the book's own words" until the first answer came back,
    // on a server that writes every answer with a model.
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()], generatedAnswers: true }));
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    expect(await screen.findByText(strings.assistantGenerated)).toBeTruthy();
    expect(screen.queryByText(strings.assistantExtractive)).toBeNull();
  });

  it("keeps focus on the ask button while the answer is on its way", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));
    await user.type(screen.getByLabelText(strings.questionLabel), "පළමු");
    const ask = screen.getByRole<HTMLButtonElement>("button", { name: strings.assistantAsk });
    // Disabling it while asking dropped focus to <body> in a browser. The
    // round trip here is too quick to see the focus move, so watch for the
    // cause: the focused button being disabled at any moment.
    let disabledUnderFocus = false;
    const watch = new MutationObserver(() => {
      if (ask.disabled && document.activeElement === ask) disabledUnderFocus = true;
    });
    watch.observe(ask, { attributes: true });
    await user.click(ask);

    expect(await screen.findByText(strings.answerFromBook)).toBeTruthy();
    watch.disconnect();
    expect(disabledUnderFocus).toBe(false);
    expect(document.activeElement).toBe(ask);
  });

  it("cues a cited sentence on another page once that page has opened", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [book()],
      studyAnswer: {
        document_id: "doc-1",
        answer: ON_PAGE_TWO,
        citations: [
          {
            passage_id: "passage-2",
            page_index: 1,
            page_label: "13",
            section: null,
            segment_ids: ["0001-s0"],
            quote: ON_PAGE_TWO,
          },
        ],
        abstained: false,
        generated: false,
      },
    });
    open(server);
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));
    await user.type(screen.getByLabelText(strings.questionLabel), "දෙවන");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));

    const citation = await waitFor(() => {
      const found = document.querySelector<HTMLButtonElement>(".assistant .citation");
      if (!found) throw new Error("no citation yet");
      return found;
    });
    await user.click(citation);

    const sentence = await screen.findByRole("button", { name: ON_PAGE_TWO });
    await waitFor(() => expect(sentence.getAttribute("aria-current")).toBe("true"));
    expect(playCalls).toHaveLength(0);
  });

  // Carried over from the study page this drawer replaced.
  it("cues a cited sentence without starting audio", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [book()],
      studyAnswer: {
        document_id: "doc-1",
        answer: FIRST,
        citations: [
          {
            passage_id: "passage-1",
            page_index: 0,
            page_label: "12",
            section: null,
            segment_ids: ["0000-s0"],
            quote: FIRST,
          },
        ],
        abstained: false,
        generated: false,
      },
    });
    open(server);
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));
    await user.type(screen.getByLabelText(strings.questionLabel), "පළමු");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));

    const citation = await waitFor(() => {
      const found = document.querySelector<HTMLButtonElement>(".assistant .citation");
      if (!found) throw new Error("no citation yet");
      return found;
    });
    await user.click(citation);

    // Cued, not played: nothing speaks over a screen reader unasked.
    const sentence = screen.getByRole("button", { name: FIRST });
    await waitFor(() => expect(sentence.getAttribute("aria-current")).toBe("true"));
    expect(playCalls).toHaveLength(0);
  });

  it("does not invent an answer when the book has none", async () => {
    const user = userEvent.setup();
    open(
      new FakeServer({
        books: [book()],
        studyAnswer: {
          document_id: "doc-1",
          answer: null,
          citations: [],
          abstained: true,
          generated: false,
        },
      }),
    );
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));
    await user.type(screen.getByLabelText(strings.questionLabel), "පිටත කරුණක්?");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));

    expect(
      await screen.findByRole("heading", { name: strings.studyAbstainedHeading }),
    ).toBeTruthy();
    expect(screen.queryByText(strings.answerFromBook)).toBeNull();
    await waitFor(() => expect(politeText()).toContain(strings.studyAbstainedHeading));
  });

  it("keeps the conversation when it is minimised", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    const toggle = screen.getByRole("button", { name: new RegExp(strings.assistantToggle) });
    await user.click(toggle);
    await user.type(screen.getByLabelText(strings.questionLabel), "කවදාද?");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));
    await screen.findByText("කවදාද?");

    await user.click(screen.getByRole("button", { name: strings.assistantMinimise }));
    // Closing hides it; somebody who shut the panel to read a paragraph should
    // find their place on returning, not a blank form.
    await user.click(toggle);
    expect(screen.getByText("කවදාද?")).toBeTruthy();
  });

  it("closes on Escape and gives focus back to the button that opened it", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });

    const toggle = screen.getByRole("button", { name: new RegExp(strings.assistantToggle) });
    await user.click(toggle);
    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(toggle.getAttribute("aria-expanded")).toBe("false"));
    expect(document.activeElement).toBe(toggle);
  });

  it("clears the conversation only when told to", async () => {
    const user = userEvent.setup();
    open(new FakeServer({ books: [book()] }));
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    await user.type(screen.getByLabelText(strings.questionLabel), "කවදාද?");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));
    await screen.findByText("කවදාද?");

    await user.click(screen.getByRole("button", { name: strings.assistantClear }));
    await waitFor(() => expect(screen.queryByText("කවදාද?")).toBeNull());
    await waitFor(() => expect(politeText()).toContain(strings.assistantCleared));
  });

  it("sends the conversation with a follow-up, so 'the list of them' means something", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    open(server);
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    const asked = () =>
      server
        .callsTo("POST", /\/documents\/doc-1\/questions$/)
        .map((call) => JSON.parse(String(call.body)) as { question: string; history?: unknown });

    await user.type(screen.getByLabelText(strings.questionLabel), "පළමු");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));
    await screen.findByText(strings.answerFromBook);

    await user.type(screen.getByLabelText(strings.questionLabel), "ඒවායේ ලැයිස්තුව");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));
    await waitFor(() => expect(asked()).toHaveLength(2));

    // A first question is sent exactly as it always was.
    expect(asked()[0]).toEqual({ question: "පළමු" });
    expect(asked()[1]).toEqual({
      question: "ඒවායේ ලැයිස්තුව",
      history: [{ question: "පළමු", answer: expect.any(String) }],
    });
  });

  it("does not send a conversation the reader cleared", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    open(server);
    await screen.findByRole("button", { name: FIRST });
    await user.click(screen.getByRole("button", { name: new RegExp(strings.assistantToggle) }));

    await user.type(screen.getByLabelText(strings.questionLabel), "පළමු");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));
    await screen.findByText(strings.answerFromBook);
    await user.click(screen.getByRole("button", { name: strings.assistantClear }));

    await user.type(screen.getByLabelText(strings.questionLabel), "දෙවන");
    await user.click(screen.getByRole("button", { name: strings.assistantAsk }));

    await waitFor(() =>
      expect(server.callsTo("POST", /\/documents\/doc-1\/questions$/)).toHaveLength(2),
    );
    const second = server.callsTo("POST", /\/documents\/doc-1\/questions$/)[1];
    // Clearing is a promise that the old topic is gone, including from the server.
    expect(JSON.parse(String(second?.body))).toEqual({ question: "දෙවන" });
  });
});
