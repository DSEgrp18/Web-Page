import userEvent from "@testing-library/user-event";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppFrame } from "../src/components/AppFrame";
import { Library } from "../src/components/Library";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage, type FakeBook } from "./fakeApi";
import { assertiveText, politeText, renderApp } from "./render";

function pdf(name = "ඉතිහාසය.pdf"): File {
  return new File([new Uint8Array([37, 80, 68, 70])], name, { type: "application/pdf" });
}

/** A prepared book with `sentences` sentences on one page. */
function book(overrides: Partial<FakeBook> = {}): FakeBook {
  return {
    document_id: "doc-1",
    filename: "ඉතිහාසය.pdf",
    version: "v1",
    pages: [readablePage(0, ["පළමු වාක්‍යය.", "දෙවන වාක්‍යය.", "තෙවන වාක්‍යය."])],
    ...overrides,
  };
}

/** Open the add-a-book dialog. */
async function openUpload(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: new RegExp(strings.addBook) }));
}

describe("the welcome", () => {
  it("explains what this is when there is nothing to show yet", async () => {
    renderApp(<Library />, new FakeServer());
    expect(await screen.findByRole("heading", { name: strings.welcomeHeading })).toBeTruthy();
    expect(screen.getByText(strings.welcomeBody)).toBeTruthy();
  });

  it("shrinks out of the way once there are books", async () => {
    renderApp(<Library />, new FakeServer({ books: [book()] }));
    await screen.findByRole("heading", { name: strings.libraryHeading });
    // The pitch is for somebody who has not started. A returning reader should
    // not scroll past it every time.
    expect(screen.queryByText(strings.welcomeBody)).toBeNull();
  });
});

describe("the shelf", () => {
  it("names the book inside the link that opens it", async () => {
    renderApp(<Library />, new FakeServer({ books: [book()] }));
    const link = await screen.findByRole("link", { name: /ඉතිහාසය\.pdf/ });
    expect(link.getAttribute("href")).toBe("/documents/doc-1");
  });

  it("prefers the reader's own name for a book over the filename", async () => {
    renderApp(<Library />, new FakeServer({ books: [book({ title: "ඉතිහාසය 11 ශ්‍රේණිය" })] }));
    expect(await screen.findByRole("heading", { name: "ඉතිහාසය 11 ශ්‍රේණිය" })).toBeTruthy();
  });

  it("searches by title and by the file that was uploaded", async () => {
    const user = userEvent.setup();
    renderApp(
      <Library />,
      new FakeServer({
        books: [
          book({ document_id: "doc-1", filename: "ඉතිහාසය.pdf" }),
          book({ document_id: "doc-2", filename: "ගණිතය.pdf", title: "Maths" }),
        ],
      }),
    );
    const search = await screen.findByRole("searchbox", { name: strings.searchLibrary });

    await user.type(search, "ගණිතය");
    // Renamed, but still findable by the file they uploaded.
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Maths" })).toBeTruthy());
    expect(screen.queryByRole("heading", { name: "ඉතිහාසය.pdf" })).toBeNull();
  });

  it("offers a way out of a search that found nothing", async () => {
    const user = userEvent.setup();
    renderApp(<Library />, new FakeServer({ books: [book()] }));
    const search = await screen.findByRole("searchbox", { name: strings.searchLibrary });

    await user.type(search, "zzzz");
    expect(await screen.findByRole("heading", { name: strings.noResultsHeading })).toBeTruthy();

    await user.click(screen.getByRole("button", { name: strings.clearSearch }));
    await screen.findByRole("heading", { name: "ඉතිහාසය.pdf" });
  });

  it("filters to what is still being prepared", async () => {
    const user = userEvent.setup();
    renderApp(
      <Library />,
      new FakeServer({
        books: [
          book({ document_id: "doc-1", filename: "සූදානම්.pdf", version: "v1" }),
          book({ document_id: "doc-2", filename: "අලුත්.pdf", version: null }),
        ],
      }),
    );
    await screen.findByRole("heading", { name: "සූදානම්.pdf" });

    await user.click(screen.getByRole("radio", { name: strings.filterProcessing }));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "සූදානම්.pdf" })).toBeNull());
    expect(screen.getByRole("heading", { name: "අලුත්.pdf" })).toBeTruthy();
  });

  it("reports how far through a book the reader is", async () => {
    renderApp(
      <Library />,
      new FakeServer({
        books: [
          book({
            reading: {
              segment_id: "0000-s2",
              segment_index: 1,
              updated_at: "2026-09-10T00:00:00Z",
              stale: false,
            },
          }),
        ],
      }),
    );
    // Two of three sentences read is 67%, announced as a measurement rather
    // than drawn as a decorative bar.
    const bar = await screen.findAllByRole("progressbar");
    expect(bar[0]?.getAttribute("aria-valuenow")).toBe("67");
  });

  it("does not call a book finished until the last sentence is reached", async () => {
    renderApp(
      <Library />,
      new FakeServer({
        books: [
          book({
            reading: {
              segment_id: "0000-s3",
              segment_index: 2,
              updated_at: "2026-09-10T00:00:00Z",
              stale: false,
            },
          }),
        ],
      }),
    );
    expect(await screen.findByText(strings.finishedReading)).toBeTruthy();
  });

  it("offers the last book read, above everything else", async () => {
    renderApp(
      <Library />,
      new FakeServer({
        books: [
          book({ document_id: "doc-1", filename: "පරණ.pdf", created_at: "2026-09-01T00:00:00Z" }),
          book({
            document_id: "doc-2",
            filename: "අලුත්.pdf",
            created_at: "2026-09-02T00:00:00Z",
            reading: {
              segment_id: "0000-s2",
              segment_index: 1,
              updated_at: "2026-09-11T00:00:00Z",
              stale: false,
            },
          }),
        ],
      }),
    );
    // The same book also appears on the shelf below, so this asserts that one
    // of its headings is the resume card rather than that only one exists.
    const headings = await screen.findAllByRole("heading", { name: /අලුත්\.pdf/ });
    expect(headings.some((heading) => heading.closest(".continue"))).toBe(true);
  });

  it("stops polling once nothing is being prepared", async () => {
    const server = new FakeServer({ books: [book()] });
    renderApp(<Library />, server);
    await screen.findByRole("link", { name: /ඉතිහාසය\.pdf/ });

    const listedOnce = server.callsTo("GET", /^\/documents$/).length;
    await new Promise((resolve) => setTimeout(resolve, 200));
    // An idle library makes no requests; a poll loop that never stops is a
    // battery and data cost paid by a reader on a phone.
    expect(server.callsTo("GET", /^\/documents$/).length).toBe(listedOnce);
  });

  it("says a book is being prepared without inventing a percentage", async () => {
    renderApp(<Library />, new FakeServer({ books: [book({ version: null })] }));
    expect(await screen.findByText(strings.stateRunning)).toBeTruthy();
    // There is no real progress to report, and a believable fake one is worse
    // than none.
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});

describe("adding a book", () => {
  it("uploads and announces its progress politely", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(<Library />, server);

    await openUpload(user);
    await user.upload(screen.getByLabelText(strings.uploadChoose), pdf());
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    await screen.findByRole("link", { name: /ඉතිහාසය\.pdf/ });
    // Progress goes to the polite region. Nothing here is urgent enough to
    // interrupt a screen reader mid-sentence.
    expect(politeText()).not.toBe("");
    expect(assertiveText()).toBe("");
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(1);
  });

  it("refuses a dropped file that is not a PDF, before sending anything", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(<Library />, server);

    await openUpload(user);

    /*
     * Dropped, not picked. The file input carries `accept="application/pdf"`,
     * so the picker filters non-PDFs out and `user.upload` honours that — the
     * change event never fires and there is nothing to reject. Drag and drop
     * ignores `accept` entirely, which is the whole reason the check in
     * `accept()` exists, and therefore the only path worth testing.
     */
    const dropzone = document.querySelector(".dropzone")!;
    const file = new File(["not a pdf"], "notes.txt", { type: "text/plain" });
    fireEvent.drop(dropzone, { dataTransfer: { files: [file], types: ["Files"] } });

    await waitFor(() => expect(assertiveText()).toBe(strings.uploadNotPdf));
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(0);
  });

  it("cannot be submitted with nothing chosen", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(<Library />, server);

    await openUpload(user);
    // Disabled rather than failing on submit: the control should not offer to
    // do something it will refuse.
    const submit = screen.getByRole("button", { name: strings.uploadSubmit });
    expect(submit.hasAttribute("disabled")).toBe(true);
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(0);
  });

  it("interrupts only for an error", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    const failing = new FakeServer();
    Object.defineProperty(failing, "fetch", {
      value: async (url: string, init: RequestInit = {}) =>
        (init.method ?? "GET") === "POST"
          ? new Response(JSON.stringify({ detail: "no" }), { status: 500 })
          : server.fetch(url, init),
    });

    renderApp(<Library />, failing);
    await openUpload(user);
    await user.upload(screen.getByLabelText(strings.uploadChoose), pdf());
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    await waitFor(() => expect(assertiveText()).toBe(strings.errorServer));
  });
});

describe("naming a book", () => {
  it("saves the reader's own name for it", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    renderApp(<Library />, server);

    await user.click(await screen.findByRole("button", { name: /නම වෙනස්.*ඉතිහාසය/ }));
    const field = await screen.findByLabelText(strings.renameLabel);
    await user.clear(field);
    await user.type(field, "ඉතිහාසය 11");
    await user.click(screen.getByRole("button", { name: strings.renameSave }));

    await waitFor(() => expect(server.callsTo("PATCH", /^\/documents\//)).toHaveLength(1));
    await screen.findByRole("heading", { name: "ඉතිහාසය 11" });
    await waitFor(() => expect(politeText()).toContain(strings.renamed));
  });
});

describe("deleting a book", () => {
  it("opens the dialog onto cancel, and Escape puts focus back", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    renderApp(<Library />, server);

    const deleteButton = await screen.findByRole("button", { name: /මකන්න.*ඉතිහාසය/ });
    await user.click(deleteButton);

    expect(await screen.findByRole("heading", { name: strings.deleteConfirmTitle })).toBeTruthy();
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: strings.deleteConfirmCancel }),
      ),
    );

    // jsdom does not synthesise Escape→cancel the way a browser does; fire the
    // same event the platform would, which ConfirmDialog listens for.
    // Three dialogs are mounted at once now (upload, rename, confirm), so
    // "the first dialog" is the wrong one. The open one is the one on screen.
    const dialog = document.querySelector("dialog[open]");
    dialog?.dispatchEvent(new Event("cancel", { cancelable: true }));

    await waitFor(() => expect(document.activeElement).toBe(deleteButton));
    expect(server.callsTo("DELETE", /\/documents\//)).toHaveLength(0);
  });

  it("deletes only after the confirm action, and announces it politely", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({ books: [book()] });
    renderApp(<Library />, server);

    await user.click(await screen.findByRole("button", { name: /මකන්න.*ඉතිහාසය/ }));
    await user.click(screen.getByRole("button", { name: strings.deleteConfirmAction }));

    await waitFor(() => expect(server.callsTo("DELETE", /\/documents\//)).toHaveLength(1));
    await waitFor(() => expect(politeText()).toContain(strings.deleted));
  });
});

describe("identity", () => {
  it("asks who the reader is before fetching anything", async () => {
    const server = new FakeServer();
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      server,
      "",
    );

    expect(screen.getByRole("heading", { name: strings.identityHeading })).toBeTruthy();
    expect(server.calls).toHaveLength(0);
  });

  it("says plainly that this is not a login", () => {
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      new FakeServer(),
      "",
    );
    // A student uploading a private textbook must not believe a name in a text
    // box is protecting it.
    expect(screen.getByText(strings.identityHelp)).toBeTruthy();
  });

  it("gets out of the way once there is one", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      server,
      "",
    );

    await user.type(screen.getByLabelText(strings.identityLabel), "sithara");
    await user.click(screen.getByRole("button", { name: strings.identitySave }));

    await screen.findByRole("heading", { name: strings.welcomeHeading });
    expect(server.calls[0]?.owner).toBe("sithara");
  });
});
