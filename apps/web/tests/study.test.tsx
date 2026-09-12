import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Study } from "../src/components/Study";
import { strings } from "../src/lib/strings";
import type { StudyAnswer } from "../src/lib/types";
import { FakeServer, readablePage } from "./fakeApi";
import { politeText, renderApp } from "./render";

const answer: StudyAnswer = {
  document_id: "doc-1",
  answer: "මෙය පොතෙන් තෝරාගත් පිළිතුරකි.",
  citations: [
    {
      passage_id: "passage-1",
      page_index: 0,
      page_label: "12",
      section: "පළමු කොටස",
      segment_ids: ["0000-s0"],
      quote: "මෙය පොතෙන් තෝරාගත් පිළිතුරකි.",
    },
  ],
  abstained: false,
};

function server(result: StudyAnswer = answer) {
  return new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["මෙය පොතෙන් තෝරාගත් පිළිතුරකි."])],
      },
    ],
    studyAnswer: result,
  });
}

describe("study mode", () => {
  it("submits a question and links its cited source without starting audio", async () => {
    const user = userEvent.setup();
    const fake = server();
    renderApp(<Study documentId="doc-1" />, fake);

    const question = await screen.findByLabelText(strings.questionLabel);
    await user.type(question, "මෙය කුමක්ද?");
    await user.click(screen.getByRole("button", { name: strings.askQuestion }));

    await screen.findByRole("heading", { name: strings.answerHeading });
    expect(screen.getAllByText(answer.answer!)).toHaveLength(2);
    expect(screen.getByRole("link", { name: strings.openCitation }).getAttribute("href")).toBe(
      "/documents/doc-1?segment=0000-s0",
    );
    expect(fake.callsTo("POST", /\/documents\/doc-1\/questions$/)[0]?.body).toBe(
      JSON.stringify({ question: "මෙය කුමක්ද?" }),
    );
    expect(fake.callsTo("GET", /\/audio$/)).toHaveLength(0);
    await waitFor(() => expect(politeText()).toContain(strings.answerFound));
  });

  it("does not invent an answer when the API abstains", async () => {
    const user = userEvent.setup();
    const fake = server({ document_id: "doc-1", answer: null, citations: [], abstained: true });
    renderApp(<Study documentId="doc-1" />, fake);

    await user.type(await screen.findByLabelText(strings.questionLabel), "පිටත කරුණක්?");
    await user.click(screen.getByRole("button", { name: strings.askQuestion }));

    expect(
      await screen.findByRole("heading", { name: strings.studyAbstainedHeading }),
    ).not.toBeNull();
    expect(screen.queryByRole("heading", { name: strings.answerHeading })).toBeNull();
    await waitFor(() => expect(politeText()).toContain(strings.studyAbstainedHeading));
  });
});
