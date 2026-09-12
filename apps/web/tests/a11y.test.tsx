import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import RootLayout from "../src/app/layout";
import { AppFrame } from "../src/components/AppFrame";
import { Bookmarks } from "../src/components/Bookmarks";
import { Library } from "../src/components/Library";
import { Reader } from "../src/components/Reader";
import { Study } from "../src/components/Study";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage } from "./fakeApi";
import { noticeText, renderApp } from "./render";

/**
 * The accessibility smoke test CLAUDE.md's CI section asks for.
 *
 * What it is: an automated check of the core reader flows against WCAG 2.2 A
 * and AA rules that can be decided from the DOM alone.
 *
 * What it is **not**, and must never be reported as: evidence that the reader
 * is usable. Automated rules catch perhaps a third of real barriers, and none
 * of the ones this project actually turns on — whether the Sinhala reads
 * naturally, whether the announcements arrive at a useful moment, whether the
 * sentence list is navigable at speed. CLAUDE.md treats inability to upload,
 * play, pause, navigate or resume with assistive technology as a release
 * blocker, and only NVDA and TalkBack in front of a person settle that.
 */

/**
 * Colour contrast needs real layout and a canvas, neither of which jsdom has,
 * so axe cannot decide it here. The palette in `globals.css` was checked by
 * hand instead, and the measured ratios are recorded there.
 */
const RULES = { "color-contrast": { enabled: false } };

const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

async function violationsIn(element: HTMLElement) {
  const results = await axe.run(element, {
    runOnly: { type: "tag", values: TAGS },
    rules: RULES,
  });
  return results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    nodes: violation.nodes.map((node) => node.html),
  }));
}

function libraryServer() {
  return new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["පළමු වාක්‍යය.", "දෙවන වාක්‍යය."])],
      },
    ],
  });
}

beforeEach(() => {
  // The real document declares this in `layout.tsx`; jsdom starts without it.
  // Asserted separately below so this line cannot paper over losing it.
  document.documentElement.lang = "si";
});

describe("the document language", () => {
  it("is declared as Sinhala on the html element", () => {
    const markup = renderToStaticMarkup(
      <RootLayout>
        <p>අන්තර්ගතය</p>
      </RootLayout>,
    );
    // Without this, NVDA and TalkBack read the Sinhala interface with an
    // English synthesiser, which is unintelligible even when the words are right.
    expect(markup).toContain('lang="si"');
  });
});

describe("no automatically detectable violations", () => {
  it("on the identity step", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      new FakeServer(),
      "",
    );
    await screen.findByRole("heading", { name: strings.identityHeading });
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on the library", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      libraryServer(),
    );
    await screen.findByRole("link", { name: /ඉතිහාසය\.pdf/ });
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on the bookmarks screen", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Bookmarks />
      </AppFrame>,
      libraryServer(),
    );
    await screen.findByRole("heading", { name: strings.bookmarksEmptyTitle });
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on a page being read", async () => {
    const user = userEvent.setup();
    const { container } = renderApp(
      <AppFrame>
        <Reader documentId="doc-1" />
      </AppFrame>,
      libraryServer(),
    );

    const sentence = await screen.findByRole("button", { name: "පළමු වාක්‍යය." });
    expect(await violationsIn(container)).toEqual([]);

    // And while something is playing, when a sentence carries aria-current and
    // the placeholder notice has appeared.
    await user.click(sentence);
    await waitFor(() => expect(sentence.getAttribute("aria-current")).toBe("true"));
    expect(await violationsIn(container)).toEqual([]);
  });

  it("in study mode", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Study documentId="doc-1" />
      </AppFrame>,
      libraryServer(),
    );
    await screen.findByLabelText(strings.questionLabel);
    expect(await violationsIn(container)).toEqual([]);
  });

  it("when a page could not be read", async () => {
    const unreadable = readablePage(0, []);
    unreadable.quality = "undecodable";
    unreadable.notes = ["මෙම පිටුව පැරණි ෆොන්ටයකින් ලියා ඇත."];
    const server = new FakeServer({
      books: [{ document_id: "doc-1", filename: "book.pdf", version: "v1", pages: [unreadable] }],
    });

    const { container } = renderApp(
      <AppFrame>
        <Reader documentId="doc-1" />
      </AppFrame>,
      server,
    );
    await screen.findByText(strings.qualityUndecodable);
    expect(await violationsIn(container)).toEqual([]);
  });

  it("when something has gone wrong", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Reader documentId="missing" />
      </AppFrame>,
      new FakeServer(),
    );
    await waitFor(() => expect(noticeText()).toContain(strings.errorNotFound));
    expect(await violationsIn(container)).toEqual([]);
  });

  it("when the delete dialog is open", async () => {
    const user = userEvent.setup();
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      libraryServer(),
    );
    await user.click(await screen.findByRole("button", { name: /මකන්න.*ඉතිහාසය/ }));
    await screen.findByRole("heading", { name: strings.deleteConfirmTitle });
    expect(await violationsIn(container)).toEqual([]);
  });
});
