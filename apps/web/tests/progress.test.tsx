import { screen, waitFor } from "@testing-library/react";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { ClassProgressSection } from "../src/components/ClassProgressSection";
import { Practice } from "../src/components/Practice";
import { Progress } from "../src/components/Progress";
import { si as strings } from "../src/lib/strings";
import type { BookProgress } from "../src/lib/types";
import { FakeServer, readablePage } from "./fakeApi";
import { renderApp } from "./render";

const HISTORY: BookProgress = {
  document_id: "doc-1",
  title: "ඉතිහාසය",
  chapters: [
    {
      title: "පළමු පරිච්ඡේදය",
      first_page: 0,
      sentences: 4,
      heard: 4,
      complete: true,
      answered: 2,
      correct: 1,
      due: 1,
    },
    {
      title: "දෙවන පරිච්ඡේදය",
      first_page: 5,
      sentences: 10,
      heard: 0,
      complete: false,
      answered: 0,
      correct: 0,
      due: 0,
    },
  ],
};

function withProgress(): FakeServer {
  const server = new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["ශ්‍රී ලංකාවේ අගනුවර කෝට්ටේ වේ.", "කොළඹ ප්‍රධාන වරාය නගරයයි."])],
      },
    ],
  });
  server.report = {
    books: [HISTORY],
    chapters_complete: 1,
    chapter_count: 2,
    due: 1,
    revise: [{ document_id: "doc-1", title: "ඉතිහාසය", quiz_id: "quiz-1", due: 1 }],
  };
  return server;
}

describe("the progress page", () => {
  it("says it all in a sentence first", async () => {
    renderApp(<Progress />, withProgress());

    expect(await screen.findByText(strings.progressSummary(1, 2, 1))).toBeTruthy();
  });

  it("gives each book a captioned table, chapter by chapter", async () => {
    renderApp(<Progress />, withProgress());

    const table = await screen.findByRole("table", {
      name: strings.progressCaption("ඉතිහාසය"),
    });
    expect(table.querySelectorAll("tbody tr")).toHaveLength(2);
    expect(table.textContent).toContain("100%");
    expect(table.textContent).toContain(strings.progressAnsweredCell(1, 2));
  });

  it("links what to revise next to the quiz, due questions only", async () => {
    renderApp(<Progress />, withProgress());

    const link = await screen.findByRole("link", { name: strings.reviseLink("ඉතිහාසය", 1) });
    expect(link.getAttribute("href")).toBe("/library/doc-1/practice?review=quiz-1");
  });

  it("says so when there is nothing yet", async () => {
    renderApp(<Progress />, new FakeServer({ books: [] }));

    expect(await screen.findByText(strings.progressNoBooks)).toBeTruthy();
  });

  it("has no automatically detectable accessibility violations", async () => {
    const { container } = renderApp(<Progress />, withProgress());
    await screen.findByRole("table");

    const results = await axe.run(container);
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});

describe("revising from the progress page", () => {
  it("asks only the questions that are due", async () => {
    const server = withProgress();
    server.quizzes.push({
      quiz_id: "quiz-1",
      document_id: "doc-1",
      for_class: false,
      status: "published",
      generator: "cloze",
      question_count: 2,
      stale: false,
      mine: true,
      created_at: "2026-09-10T00:00:00Z",
      creator: "reader-one",
      answers: [
        { question_id: "q1", choice: 0, correct: true, due: false },
        { question_id: "q2", choice: 1, correct: false, due: true },
      ],
      questions: [
        {
          question_id: "q1",
          question: "_____ ශ්‍රී ලංකාවේ අගනුවරයි.",
          options: ["කෝට්ටේ", "කොළඹ"],
          page_label: "1",
          answer: 0,
        },
        {
          question_id: "q2",
          question: "_____ ප්‍රධාන වරාය නගරයයි.",
          options: ["ගාල්ල", "කොළඹ"],
          page_label: "1",
          answer: 1,
        },
      ],
    });
    renderApp(<Practice documentId="doc-1" review="quiz-1" />, server);

    expect(await screen.findByRole("heading", { name: strings.questionOf(1, 1) })).toBeTruthy();
    expect(screen.getByText(/ප්‍රධාන වරාය/)).toBeTruthy();
  });
});

describe("a class's progress, for its teacher", () => {
  it("lists only students who share, and says how many do not", async () => {
    const server = new FakeServer({ books: [] });
    server.classProgressReport = {
      class_id: "cls-a",
      name: "A",
      students: [{ display_name: "නිමාලි", books: [HISTORY] }],
      not_sharing: 2,
    };
    renderApp(<ClassProgressSection classId="cls-a" />, server);

    expect(await screen.findByText(strings.classNotSharing(2))).toBeTruthy();
    expect(screen.getByText("නිමාලි")).toBeTruthy();
    expect(screen.getByRole("button", { name: strings.classProgressDownload })).toBeTruthy();
  });

  it("says so when nobody has chosen to share", async () => {
    renderApp(<ClassProgressSection classId="cls-a" />, new FakeServer({ books: [] }));

    await waitFor(() => expect(screen.getByText(strings.classProgressNobody)).toBeTruthy());
  });
});
