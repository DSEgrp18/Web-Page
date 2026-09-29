import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { BookReports } from "../src/components/BookReports";
import { BookSearch } from "../src/components/BookSearch";
import { PasteText } from "../src/components/PasteText";
import { ReportForm } from "../src/components/ReportForm";
import { si as strings } from "../src/lib/strings";
import { FakeServer, readablePage } from "./fakeApi";
import { noticeText, politeText, renderApp } from "./render";

function oneBook(): FakeServer {
  return new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["ශ්‍රී ලංකාවේ අගනුවර කෝට්ටේ වේ.", "කොළඹ ප්‍රධාන වරාය නගරයයි."])],
      },
    ],
  });
}

async function violations(container: HTMLElement): Promise<string[]> {
  return (await axe.run(container)).violations.map((v) => v.id);
}

describe("pasting text", () => {
  it("says it is read in sections, and sends the text and name", async () => {
    const user = userEvent.setup();
    const server = oneBook();
    renderApp(<PasteText />, server);

    expect(screen.getByText(strings.pasteHow)).toBeTruthy();
    await user.type(screen.getByLabelText(strings.pasteTitleLabel), "සටහන්");
    await user.type(screen.getByLabelText(strings.pasteTextLabel), "කොළඹ නගරයයි.");
    await user.click(screen.getByRole("button", { name: strings.pasteAction }));

    await waitFor(() => expect(server.pasted).toEqual([{ text: "කොළඹ නගරයයි.", title: "සටහන්" }]));
  });

  it("says so when there is nothing to paste, without sending", async () => {
    const user = userEvent.setup();
    const server = oneBook();
    renderApp(<PasteText />, server);

    await user.click(screen.getByRole("button", { name: strings.pasteAction }));

    expect(noticeText()).toContain(strings.pasteEmpty);
    expect(server.pasted).toEqual([]);
  });
});

describe("searching a book", () => {
  it("lists its own sentences, then related passages, each opening the book cued", async () => {
    const user = userEvent.setup();
    const server = oneBook();
    server.searchResults = {
      query: "කොළඹ",
      exact: [
        {
          segment_id: "0000-s1",
          page_index: 0,
          page_label: "1",
          text: "කොළඹ ප්‍රධාන වරාය නගරයයි.",
        },
      ],
      related: [{ segment_id: "0000-s0", page_index: 0, page_label: "1", text: "ශ්‍රී ලංකාවේ" }],
    };
    const { container } = renderApp(<BookSearch documentId="doc-1" />, server);

    await user.type(screen.getByLabelText(strings.searchLabel), "කොළඹ");
    await user.click(screen.getByRole("button", { name: strings.searchAction }));

    const exact = await screen.findByRole("heading", { name: strings.searchExactHeading(1) });
    expect(exact).toBeTruthy();
    expect(screen.getByRole("heading", { name: strings.searchRelatedHeading })).toBeTruthy();
    const links = screen.getAllByRole("link", { name: strings.searchResultPage("1") });
    expect(links[0]!.getAttribute("href")).toBe("/library/doc-1?segment=0000-s1");
    await waitFor(() => expect(politeText()).toContain(strings.searchFound(1, 1)));
    expect(await violations(container)).toEqual([]);
  });

  it("labels the way back as going back to the book", async () => {
    renderApp(<BookSearch documentId="doc-1" />, oneBook());
    const back = await screen.findByRole("link", { name: strings.backToReader });
    expect(back.getAttribute("href")).toBe("/library/doc-1");
    expect(screen.queryByRole("link", { name: strings.backToLibrary })).toBeNull();
  });

  it("says plainly when nothing matched", async () => {
    const user = userEvent.setup();
    const server = oneBook();
    server.searchResults = { query: "x", exact: [], related: [] };
    renderApp(<BookSearch documentId="doc-1" />, server);

    await user.type(screen.getByLabelText(strings.searchLabel), "x");
    await user.click(screen.getByRole("button", { name: strings.searchAction }));

    expect(
      await screen.findByText(strings.searchNothing, { selector: ".account-page > p" }),
    ).toBeTruthy();
  });
});

describe("reporting a problem", () => {
  it("about a sentence goes with the book and the sentence, and says who reads it", async () => {
    const user = userEvent.setup();
    const server = oneBook();
    const { container } = renderApp(
      <ReportForm target={{ document: "doc-1", segment: "0000-s0" }} />,
      server,
    );

    expect(screen.getByText(strings.reportWhoBook)).toBeTruthy();
    const pronunciation = screen.getByRole("radio", {
      name: strings.reportKinds.pronunciation,
    }) as HTMLInputElement;
    expect(pronunciation.checked).toBe(true);
    expect(await violations(container)).toEqual([]);
    await user.type(screen.getByLabelText(strings.reportMessageLabel), "වැරදියි");
    await user.click(screen.getByRole("button", { name: strings.reportSend }));

    expect(await screen.findByRole("heading", { name: strings.reportSent })).toBeTruthy();
    expect(server.reports).toEqual([
      { kind: "pronunciation", message: "වැරදියි", document_id: "doc-1", segment_id: "0000-s0" },
    ]);
    // Back to the sentence, and saying so: it used to read "to the book list".
    const back = screen.getByRole("link", { name: strings.backToReader });
    expect(back.getAttribute("href")).toBe("/library/doc-1?segment=0000-s0");
  });

  it("needs a few words first", async () => {
    const user = userEvent.setup();
    const server = oneBook();
    renderApp(<ReportForm target={{ kind: "accessibility" }} />, server);

    expect(screen.getByText(strings.reportWhoSite)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: strings.reportSend }));

    expect(noticeText()).toContain(strings.reportMessageRequired);
    expect(server.reports).toEqual([]);
  });
});

describe("the reports on a book", () => {
  it("are listed for its owner, with the sentence and no name", async () => {
    const server = oneBook();
    server.bookReports = [
      {
        report_id: "rpt-1",
        kind: "pronunciation",
        message: "අගනුවර වැරදියට කියවේ",
        segment_id: "0000-s0",
        sentence: "ශ්‍රී ලංකාවේ අගනුවර කෝට්ටේ වේ.",
        quiz_id: null,
        question_id: null,
        created_at: "2026-09-27T00:00:00Z",
      },
    ];
    renderApp(<BookReports documentId="doc-1" />, server);

    expect(
      await screen.findByRole("heading", { name: strings.reportKinds.pronunciation }),
    ).toBeTruthy();
    expect(screen.getByText("අගනුවර වැරදියට කියවේ")).toBeTruthy();
  });

  it("says when there are none", async () => {
    renderApp(<BookReports documentId="doc-1" />, oneBook());

    expect(await screen.findByText(strings.reportsNone)).toBeTruthy();
  });
});
