import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it } from "vitest";

import RootLayout from "../src/app/layout";
import { AppFrame } from "../src/components/AppFrame";
import { Bookmarks } from "../src/components/Bookmarks";
import { ClassDetail } from "../src/components/ClassDetail";
import { Classes } from "../src/components/Classes";
import { Library } from "../src/components/Library";
import { Reader } from "../src/components/Reader";
import { ShareBook } from "../src/components/ShareBook";
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
 * so axe cannot decide it here. It is checked twice elsewhere: the token pairs
 * in tokens.contrast.test.ts, and the rendered screens in both themes by
 * browser-tests/a11y.spec.cjs.
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

/** A teacher with one class, one student waiting, and a book with a page to decide. */
function classServer() {
  const server = libraryServer();
  server.teachers.add("usr-teacher");
  server.accounts.push({
    user_id: "usr-teacher",
    email: "t@example.lk",
    password: "x",
    display_name: "සුනිල්",
  });
  server.classes.push({
    class_id: "cls-a",
    name: "10 ශ්‍රේණිය",
    join_code: "12345678",
    teacher: "usr-teacher",
    members: [
      {
        user_id: "usr-student",
        display_name: "නිමලි",
        state: "pending",
        share_progress: false,
        joined_at: "2026-09-10T00:00:00Z",
      },
    ],
  });
  server.reviews["doc-1"] = [
    { page_index: 0, page_label: "1", quality: "needs_review", notes: [], decision: null },
  ];
  return server;
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
  it("when signed out", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      new FakeServer(),
      "",
    );
    await screen.findByRole("heading", { name: strings.signedOutHeading });
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

  it("on a book whose preparation failed", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      new FakeServer({
        books: [
          {
            document_id: "doc-1",
            filename: "ඉතිහාසය.pdf",
            version: null,
            pages: [],
            job: { state: "failed", stage: "stalled", can_retry: true },
          },
        ],
      }),
    );
    await screen.findByText(strings.failedStalled);
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on the classes screen, as a teacher", async () => {
    const server = classServer();
    const { container } = renderApp(
      <AppFrame>
        <Classes />
      </AppFrame>,
      server,
      "usr-teacher",
    );
    await screen.findByRole("link", { name: "10 ශ්‍රේණිය" });
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on a class, with a student waiting", async () => {
    const { container } = renderApp(
      <AppFrame>
        <ClassDetail classId="cls-a" />
      </AppFrame>,
      classServer(),
      "usr-teacher",
    );
    await screen.findByRole("table");
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on a class, showing a student's new recovery code", async () => {
    const user = userEvent.setup();
    const server = classServer();
    server.classes[0]!.members[0]!.state = "active";
    const { container } = renderApp(
      <AppFrame>
        <ClassDetail classId="cls-a" />
      </AppFrame>,
      server,
      "usr-teacher",
    );
    await user.click(await screen.findByRole("button", { name: strings.resetNamed("නිමලි") }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: strings.resetConfirmAction }));
    await screen.findByRole("heading", { name: strings.resetCodeHeading("නිමලි") });
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on the library, telling a student about a teacher's reset code", async () => {
    const server = libraryServer();
    server.resetNotices["reader-one"] = {
      teacher_name: "සුනිල්",
      issued_at: "2026-09-10T08:00:00Z",
      used: false,
    };
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      server,
    );
    await screen.findByRole("heading", { name: strings.resetNoticeHeading });
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on sharing a book, with a page to decide", async () => {
    const { container } = renderApp(
      <AppFrame>
        <ShareBook documentId="doc-1" />
      </AppFrame>,
      classServer(),
      "usr-teacher",
    );
    await screen.findByRole("radio", { name: strings.pageAccept });
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

  it("when the contents sheet is open", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [
        {
          document_id: "doc-1",
          filename: "ඉතිහාසය.pdf",
          version: "v1",
          pages: [readablePage(0, ["පළමු වාක්‍යය."]), readablePage(1, ["දෙවන වාක්‍යය."])],
          chapters: [
            { title: "කාර්මික විප්ලවය", number: "01", page_index: 0 },
            { title: "ජාතික පුනරුදය", number: "02", page_index: 1 },
          ],
        },
      ],
    });
    const { container } = renderApp(
      <AppFrame>
        <Reader documentId="doc-1" />
      </AppFrame>,
      server,
    );
    await screen.findByRole("button", { name: "පළමු වාක්‍යය." });
    // The header's current chapter and the contents button, closed.
    expect(await violationsIn(container)).toEqual([]);

    await user.click(screen.getByRole("button", { name: strings.contentsOpen }));
    await screen.findByRole("navigation", { name: strings.contentsHeading });
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
