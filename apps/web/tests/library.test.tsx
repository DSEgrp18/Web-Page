import userEvent from "@testing-library/user-event";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppFrame } from "../src/components/AppFrame";
import { Library } from "../src/components/Library";
import { strings } from "../src/lib/strings";
import { FakeServer, OWNER, readablePage, type FakeBook } from "./fakeApi";
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
    await screen.findByRole("heading", { name: strings.browseBooks });
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

  it("returns focus to the live add button after the first upload", async () => {
    const user = userEvent.setup();
    renderApp(<Library />, new FakeServer());

    await openUpload(user);
    await user.upload(screen.getByLabelText(strings.uploadChoose), pdf());
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    const add = await screen.findByRole("button", { name: strings.addBook });
    await waitFor(() => expect(document.activeElement).toBe(add));
  });

  it("announces the selected filename for one file", async () => {
    const user = userEvent.setup();
    renderApp(<Library />, new FakeServer());

    await openUpload(user);
    await user.upload(screen.getByLabelText(strings.uploadChoose), pdf("පාඩම.pdf"));

    await waitFor(() => expect(politeText()).toContain("පාඩම.pdf"));
  });

  it("refuses an unsupported dropped file before sending anything", async () => {
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

    await waitFor(() => expect(assertiveText()).toBe(strings.uploadUnsupported));
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(0);
  });

  it("uploads multiple supported files as separate documents", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(<Library />, server);

    await openUpload(user);
    const docx = new File(["word"], "සටහන්.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    await user.upload(screen.getByLabelText(strings.uploadChoose), [pdf(), docx]);
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    await screen.findByRole("link", { name: /සටහන්\.docx/ });
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(2);
  });

  it("retries only files that did not upload", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    // The wrapper below answers from `server`, so that is the one signed in.
    server.signedInAs = OWNER;
    const flaky = new FakeServer();
    let postAttempts = 0;
    Object.defineProperty(flaky, "fetch", {
      value: async (url: string, init: RequestInit = {}) => {
        if ((init.method ?? "GET") === "POST") {
          postAttempts += 1;
          if (postAttempts === 2) {
            return new Response(JSON.stringify({ detail: "retry" }), { status: 500 });
          }
        }
        return server.fetch(url, init);
      },
    });
    renderApp(<Library />, flaky);

    await openUpload(user);
    const docx = new File(["word"], "සටහන්.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    await user.upload(screen.getByLabelText(strings.uploadChoose), [pdf(), docx]);
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));
    await waitFor(() => expect(assertiveText()).toBe(strings.errorServer));

    const retryList = document.querySelector(".upload-file-list")?.textContent ?? "";
    expect(retryList).not.toContain("ඉතිහාසය.pdf");
    expect(retryList).toContain("සටහන්.docx");
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    await screen.findByRole("link", { name: /සටහන්\.docx/ });
    expect(postAttempts).toBe(3);
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(2);
    expect(screen.getAllByRole("heading", { name: "ඉතිහාසය.pdf" })).toHaveLength(1);
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

describe("a book that is not ready", () => {
  /** A book still without a version, whose latest job is as given. */
  function unready(job: FakeBook["job"]): FakeBook {
    return book({ version: null, job });
  }

  /** Longer than the library's poll interval, so a poll would have happened. */
  const afterAPoll = () => new Promise((resolve) => setTimeout(resolve, 1700));

  it("says which page of which stage it is on", async () => {
    renderApp(
      <Library />,
      new FakeServer({
        books: [
          unready({ state: "running", stage: "recognising", pages_done: 12, pages_total: 168 }),
        ],
      }),
    );

    expect(
      await screen.findByText(`${strings.stageRecognising}: ${strings.ofPages(12, 168)}`),
    ).toBeTruthy();
  });

  it("says a failed book stopped, and why, instead of preparing for ever", async () => {
    const server = new FakeServer({
      books: [unready({ state: "failed", stage: "stalled", can_retry: true })],
    });
    renderApp(<Library />, server);

    expect(await screen.findByText(strings.stateFailed)).toBeTruthy();
    expect(screen.getByText(strings.failedStalled)).toBeTruthy();
    expect(screen.queryByText(strings.stateRunning)).toBeNull();
    expect(screen.getByRole("button", { name: /නැවත උත්සාහ.*ඉතිහාසය/ })).toBeTruthy();

    // Nothing is being prepared, so nothing is polled.
    await afterAPoll();
    expect(server.callsTo("GET", /^\/documents$/)).toHaveLength(1);
  });

  it("does not offer to try a file that was rejected for itself", async () => {
    renderApp(
      <Library />,
      new FakeServer({
        books: [unready({ state: "failed", stage: "rejected", can_retry: false })],
      }),
    );

    expect(await screen.findByText(strings.failedRejected)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /නැවත උත්සාහ/ })).toBeNull();
  });

  it("tries again, says so, and keeps focus on the book", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [unready({ state: "failed", stage: "stalled", can_retry: true })],
    });
    renderApp(<Library />, server);

    await user.click(await screen.findByRole("button", { name: /නැවත උත්සාහ.*ඉතිහාසය/ }));

    await waitFor(() => expect(server.callsTo("POST", /\/retry$/)).toHaveLength(1));
    await waitFor(() => expect(politeText()).toContain(strings.retrying));
    await screen.findByText(strings.stateRunning);
    // The button is gone with the failure; focus is on the book, not the page.
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "ඉතිහාසය.pdf" }));
  });

  it("announces a book that fails while the reader waits", async () => {
    const server = new FakeServer({ books: [unready({ state: "running" })] });
    renderApp(<Library />, server);
    await screen.findByText(strings.stateRunning);

    server.books[0]!.job = { state: "failed", stage: "stalled", can_retry: true };
    await afterAPoll();

    await waitFor(() => expect(politeText()).toContain(strings.bookFailed("ඉතිහාසය.pdf")));
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

describe("signed out", () => {
  it("asks the reader to sign in, and fetches no books", async () => {
    const server = new FakeServer({ books: [book()] });
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      server,
      "",
    );

    expect(await screen.findByRole("heading", { name: strings.signedOutHeading })).toBeTruthy();
    expect(screen.getByRole("link", { name: strings.signInAction }).getAttribute("href")).toBe(
      "/sign-in",
    );
    expect(server.calls.filter((call) => !call.path.startsWith("/auth/"))).toEqual([]);
  });

  it("sends the reader back to the page they asked for after signing in", async () => {
    window.history.replaceState(null, "", "/bookmarks");
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      new FakeServer(),
      "",
    );

    const link = await screen.findByRole("link", { name: strings.signInAction });
    expect(link.getAttribute("href")).toBe("/sign-in?next=%2Fbookmarks");
  });

  it("gets out of the way for a reader with a session", async () => {
    const server = new FakeServer();
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      server,
    );

    await screen.findByRole("heading", { name: strings.welcomeHeading });
    expect(screen.queryByRole("heading", { name: strings.signedOutHeading })).toBeNull();
  });
});
