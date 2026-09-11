import userEvent from "@testing-library/user-event";
import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppFrame } from "../src/components/AppFrame";
import { Library } from "../src/components/Library";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage } from "./fakeApi";
import { assertiveText, noticeText, politeText, renderApp } from "./render";

function pdf(name = "ඉතිහාසය.pdf"): File {
  return new File([new Uint8Array([37, 80, 68, 70])], name, { type: "application/pdf" });
}

describe("the library", () => {
  it("says it is empty rather than showing nothing", async () => {
    renderApp(<Library />, new FakeServer());
    expect(await screen.findByText(strings.libraryEmpty)).toBeTruthy();
  });

  it("lists a book with its name inside the link that opens it", async () => {
    const server = new FakeServer({
      books: [
        {
          document_id: "doc-1",
          filename: "ඉතිහාසය.pdf",
          version: "v1",
          pages: [readablePage(0, ["පළමු වාක්‍යය."])],
        },
      ],
    });
    renderApp(<Library />, server);

    // Not five links all called "open": each one says which book.
    const link = await screen.findByRole("link", { name: /ඉතිහාසය\.pdf/ });
    expect(link.getAttribute("href")).toBe("/documents/doc-1");
  });

  it("uploads a book and announces its progress politely", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(<Library />, server);

    await user.upload(screen.getByLabelText(strings.uploadLabel), pdf());
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    await screen.findByRole("link", { name: /ඉතිහාසය\.pdf/ });
    // Progress goes to the polite region. Nothing here is urgent enough to
    // interrupt a screen reader mid-sentence.
    expect(politeText()).not.toBe("");
    expect(assertiveText()).toBe("");
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(1);
  });

  it("refuses to upload nothing, and says so", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    renderApp(<Library />, server);

    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    await waitFor(() => expect(noticeText()).toContain(strings.uploadNoFile));
    expect(server.callsTo("POST", /^\/documents$/)).toHaveLength(0);
  });

  it("interrupts only for an error", async () => {
    const user = userEvent.setup();
    const server = new FakeServer();
    const failing = new FakeServer();
    // Every POST fails; everything else behaves.
    Object.defineProperty(failing, "fetch", {
      value: async (url: string, init: RequestInit = {}) =>
        (init.method ?? "GET") === "POST"
          ? new Response(JSON.stringify({ detail: "no" }), { status: 500 })
          : server.fetch(url, init),
    });

    renderApp(<Library />, failing);
    await user.upload(screen.getByLabelText(strings.uploadLabel), pdf());
    await user.click(screen.getByRole("button", { name: strings.uploadSubmit }));

    await waitFor(() => expect(assertiveText()).toBe(strings.errorServer));
    // And it stays on screen as something to read and act on, not just a
    // sentence that has already been spoken.
    expect(noticeText()).toContain(strings.errorServer);
  });

  it("stops polling once nothing is being prepared", async () => {
    const server = new FakeServer({
      books: [
        {
          document_id: "doc-1",
          filename: "book.pdf",
          version: "v1",
          pages: [readablePage(0, ["වාක්‍යය."])],
        },
      ],
    });
    renderApp(<Library />, server);
    await screen.findByRole("link", { name: /book\.pdf/ });

    const listedOnce = server.callsTo("GET", /^\/documents$/).length;
    await new Promise((resolve) => setTimeout(resolve, 200));
    // An idle library makes no requests; a poll loop that never stops is a
    // battery and data cost paid by a reader on a phone.
    expect(server.callsTo("GET", /^\/documents$/).length).toBe(listedOnce);
  });

  it("opens the delete dialog onto cancel, and Escape puts focus back", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [
        {
          document_id: "doc-1",
          filename: "ඉතිහාසය.pdf",
          version: "v1",
          pages: [readablePage(0, ["වාක්‍යය."])],
        },
      ],
    });
    renderApp(<Library />, server);

    const deleteButton = await screen.findByRole("button", { name: /මකන්න.*ඉතිහාසය/ });
    await user.click(deleteButton);

    expect(await screen.findByRole("heading", { name: strings.deleteConfirmTitle })).toBeTruthy();
    expect(screen.getByText(strings.deleteConfirmBody("ඉතිහාසය.pdf"))).toBeTruthy();
    await waitFor(() =>
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: strings.deleteConfirmCancel }),
      ),
    );

    // jsdom does not synthesise Escape→cancel the way a browser does; fire the
    // same event the platform would, which ConfirmDialog listens for.
    const dialog = document.querySelector("dialog");
    expect(dialog?.open).toBe(true);
    dialog?.dispatchEvent(new Event("cancel", { cancelable: true }));

    await waitFor(() => expect(dialog?.open).toBe(false));
    expect(document.activeElement).toBe(deleteButton);
    expect(server.callsTo("DELETE", /\/documents\//)).toHaveLength(0);
  });

  it("deletes only after the confirm action, and announces it politely", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [
        {
          document_id: "doc-1",
          filename: "ඉතිහාසය.pdf",
          version: "v1",
          pages: [readablePage(0, ["වාක්‍යය."])],
        },
      ],
    });
    renderApp(<Library />, server);

    const deleteButton = await screen.findByRole("button", { name: /මකන්න.*ඉතිහාසය/ });
    await user.click(deleteButton);
    await user.click(screen.getByRole("button", { name: strings.deleteConfirmAction }));

    await waitFor(() => expect(server.callsTo("DELETE", /\/documents\//)).toHaveLength(1));
    await waitFor(() => expect(politeText()).toContain(strings.deleted));
    expect(screen.queryByRole("heading", { name: strings.deleteConfirmTitle })).toBeNull();
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

    await screen.findByText(strings.libraryEmpty);
    expect(server.calls[0]?.owner).toBe("sithara");
  });
});
