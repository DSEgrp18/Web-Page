import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Bookmarks } from "../src/components/Bookmarks";
import { strings } from "../src/lib/strings";
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
    expect(screen.getByRole("link", { name: strings.bookmarkOpen }).getAttribute("href")).toBe(
      "/documents/doc-1?segment=0000-s0",
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
