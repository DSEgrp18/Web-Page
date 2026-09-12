import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Reader } from "../src/components/Reader";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage, type FakeBook } from "./fakeApi";
import { politeText, renderApp } from "./render";

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
});
