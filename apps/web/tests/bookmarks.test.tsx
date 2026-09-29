import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Bookmarks } from "../src/components/Bookmarks";
import { si as strings } from "../src/lib/strings";
import type { Bookmark } from "../src/lib/types";
import { FakeServer, readablePage } from "./fakeApi";
import { politeText, renderApp } from "./render";

const bookmark: Bookmark = {
  bookmark_id: "bmk-1",
  document_id: "doc-1",
  segment_id: "0000-s0",
  note: null,
  created_at: "2026-09-09T00:00:00Z",
  document_version: "v1",
  stale: false,
  segment_found: true,
  page_index: 0,
  page_label: "12",
  display_text: "පළමු වාක්‍යය.",
};

function serverWithBookmarks(bookmarks: Bookmark[] = [bookmark]) {
  return new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["පළමු වාක්‍යය."], "12")],
      },
    ],
    bookmarks,
  });
}

describe("bookmarks screen", () => {
  it("shows the saved sentence and a link that opens it without autoplay", async () => {
    renderApp(<Bookmarks />, serverWithBookmarks());

    expect(await screen.findByRole("heading", { name: strings.bookmarksHeading })).toBeTruthy();
    expect(screen.getByText(bookmark.display_text!)).toBeTruthy();
    // Named with its book and page: a list of bookmarks is otherwise a list
    // of identical links.
    const open = screen.getByRole("link", { name: /සලකුණු කළ තැන විවෘත කරන්න.*ඉතිහාසය\.pdf.*12/ });
    expect(open.textContent).toContain(strings.bookmarkOpen);
    expect(open.getAttribute("href")).toBe("/library/doc-1?segment=0000-s0");
  });

  it("groups under the reader's own name for the book", async () => {
    const server = serverWithBookmarks();
    server.books[0]!.title = "ඉතිහාසය 11";
    renderApp(<Bookmarks />, server);

    expect(await screen.findByRole("heading", { name: "ඉතිහාසය 11" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: strings.bookmarkRemoveNamed("ඉතිහාසය 11", "12") }),
    ).toBeTruthy();
  });

  it("moves focus to the book, or to the page, once a bookmark is removed", async () => {
    const user = userEvent.setup();
    const second = { ...bookmark, bookmark_id: "bmk-2", segment_id: "0000-s1" };
    const server = serverWithBookmarks([bookmark, second]);
    renderApp(<Bookmarks />, server);

    const [first] = await screen.findAllByRole("button", {
      name: strings.bookmarkRemoveNamed("ඉතිහාසය.pdf", "12"),
    });
    await user.click(first!);
    // Another bookmark is left in the book: its heading.
    await waitFor(() =>
      expect(document.activeElement).toBe(screen.getByRole("heading", { name: "ඉතිහාසය.pdf" })),
    );

    await user.click(
      screen.getByRole("button", { name: strings.bookmarkRemoveNamed("ඉතිහාසය.pdf", "12") }),
    );
    // The book's last one: the page's own heading.
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("heading", { name: strings.bookmarksHeading }),
      ),
    );
  });

  it("uses a specifically named button to remove a bookmark", async () => {
    const user = userEvent.setup();
    const server = serverWithBookmarks();
    renderApp(<Bookmarks />, server);

    const remove = await screen.findByRole("button", {
      name: strings.bookmarkRemoveNamed("ඉතිහාසය.pdf", "12"),
    });
    await user.click(remove);

    await waitFor(() => expect(server.bookmarks).toEqual([]));
    expect(politeText()).toBe(strings.bookmarkRemoved);
    expect(await screen.findByRole("heading", { name: strings.bookmarksEmptyTitle })).toBeTruthy();
  });

  it("labels a stale bookmark instead of presenting it as current", async () => {
    renderApp(<Bookmarks />, serverWithBookmarks([{ ...bookmark, stale: true }]));
    expect(await screen.findByText(strings.bookmarkStale)).toBeTruthy();
  });
});
