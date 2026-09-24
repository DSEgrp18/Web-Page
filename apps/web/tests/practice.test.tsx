import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { describe, expect, it } from "vitest";

import { Practice } from "../src/components/Practice";
import { strings } from "../src/lib/strings";
import { FakeServer, readablePage } from "./fakeApi";
import { noticeText, politeText, renderApp } from "./render";

const TEACHER = "usr-teacher";

function library(): FakeServer {
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
  server.teachers.add(TEACHER);
  return server;
}

async function startedQuiz(user: ReturnType<typeof userEvent.setup>, server = library()) {
  renderApp(<Practice documentId="doc-1" />, server);
  await user.click(await screen.findByRole("button", { name: strings.makeQuiz }));
  await screen.findByRole("heading", { name: strings.questionOf(1, 2) });
  return server;
}

describe("practising on a book", () => {
  it("says how the questions were made", async () => {
    renderApp(<Practice documentId="doc-1" />, library());

    expect(await screen.findByText(strings.practiceHow)).toBeTruthy();
    expect(await screen.findByText(strings.noQuizzes)).toBeTruthy();
  });

  it("asks one question at a time, as a group named by the question", async () => {
    const user = userEvent.setup();
    await startedQuiz(user);

    const group = screen.getByRole("group");
    // The blank is spoken as a word, not as five underscores.
    expect(group.textContent).toContain(strings.blankWord);
    expect(within(group).getAllByRole("radio")).toHaveLength(4);
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: strings.questionOf(1, 2) }),
    );
  });

  it("checks only when asked, never on choosing", async () => {
    const user = userEvent.setup();
    const server = await startedQuiz(user);

    await user.click(screen.getByRole("radio", { name: "කෝට්ටේ" }));
    expect(server.callsTo("POST", /\/answers$/)).toEqual([]);

    await user.click(screen.getByRole("button", { name: strings.checkAnswer }));

    await waitFor(() => expect(politeText()).toContain(strings.rightAnswer));
    const source = screen.getByRole("link", { name: strings.hearSource });
    expect(source.getAttribute("href")).toBe("/library/doc-1?segment=0000-s0");
  });

  it("says the right answer when the choice was wrong", async () => {
    const user = userEvent.setup();
    await startedQuiz(user);

    await user.click(screen.getByRole("radio", { name: "ගාල්ල" }));
    await user.click(screen.getByRole("button", { name: strings.checkAnswer }));

    expect(
      await screen.findByText(strings.wrongAnswer("කෝට්ටේ"), { selector: "p.notice" }),
    ).toBeTruthy();
  });

  it("asks for a choice before checking", async () => {
    const user = userEvent.setup();
    const server = await startedQuiz(user);

    await user.click(screen.getByRole("button", { name: strings.checkAnswer }));

    expect(noticeText()).toContain(strings.chooseAnswer);
    expect(server.callsTo("POST", /\/answers$/)).toEqual([]);
  });

  it("ends with the score", async () => {
    const user = userEvent.setup();
    await startedQuiz(user);

    await user.click(screen.getByRole("radio", { name: "කෝට්ටේ" }));
    await user.click(screen.getByRole("button", { name: strings.checkAnswer }));
    await user.click(await screen.findByRole("button", { name: strings.nextQuestion }));
    await user.click(await screen.findByRole("radio", { name: "යාපනය" }));
    await user.click(screen.getByRole("button", { name: strings.checkAnswer }));
    await user.click(await screen.findByRole("button", { name: strings.finishQuiz }));

    expect(await screen.findByRole("heading", { name: strings.quizScore(1, 2) })).toBeTruthy();
  });

  it("has no detectable accessibility violations mid-question", async () => {
    const user = userEvent.setup();
    document.documentElement.lang = "si";
    await startedQuiz(user);
    await user.click(screen.getByRole("radio", { name: "කෝට්ටේ" }));
    await user.click(screen.getByRole("button", { name: strings.checkAnswer }));
    await screen.findByRole("link", { name: strings.hearSource });

    const results = await axe.run(document.body, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations.map((v) => v.id)).toEqual([]);
  });
});

describe("a teacher's class quiz", () => {
  it("is reviewed, trimmed and published before the class sees it", async () => {
    const user = userEvent.setup();
    const server = library();
    renderApp(<Practice documentId="doc-1" />, server, TEACHER);

    await user.click(await screen.findByRole("button", { name: strings.makeClassQuiz }));
    await screen.findByRole("heading", { name: strings.reviewQuiz });
    expect(screen.getByText(strings.correctIs("කෝට්ටේ"))).toBeTruthy();

    await user.click(screen.getByRole("button", { name: strings.removeQuestion(2) }));
    await waitFor(() => expect(server.quizzes[0]!.questions).toHaveLength(1));
    await user.click(screen.getByRole("button", { name: strings.publishQuiz }));

    await waitFor(() => expect(server.quizzes[0]!.status).toBe("published"));
    expect(politeText()).toContain(strings.quizPublished);
  });

  it("is not offered to a student", async () => {
    renderApp(<Practice documentId="doc-1" />, library());

    await screen.findByRole("button", { name: strings.makeQuiz });
    expect(screen.queryByRole("button", { name: strings.makeClassQuiz })).toBeNull();
  });
});
