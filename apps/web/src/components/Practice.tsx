"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import type { AnswerResult, QuizDetail, QuizSummary } from "@/lib/types";
import { useStrings } from "@/components/LocaleProvider";
import { Quoted } from "@/components/BookText";

/** What stands for the missing word in a question, as the API writes it. */
const BLANK = "_____";

/** How often to look again while a model drafts, in milliseconds. */
const POLL_MS = 10_000;

/** A right answer is plain news; a wrong one is set apart. */
const RESULT = { right: "notice", wrong: "notice notice-warn" } as const;

type QuizAttempt = {
  question_id: string;
  choice: number;
  correct: boolean;
  segment_id: string | null;
};

/**
 * Practice questions on one book: the quizzes, making one, and taking one.
 *
 * Built for a screen reader first. One question per screen, as a native radio
 * group inside a fieldset whose legend is the question, so arrowing through
 * the options never submits anything; an explicit Check button does. The
 * result is static text, said once. There is no time limit anywhere.
 */
export function Practice({
  documentId,
  review,
  resume,
}: {
  documentId: string;
  review?: string;
  /** Back from the reader: this quiz, from this question (0-based). */
  resume?: { quiz: string; question: number };
}) {
  const strings = useStrings();
  const { api, account } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [quizzes, setQuizzes] = useState<QuizSummary[] | null>(null);
  const [open, setOpen] = useState<QuizDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [startAt, setStartAt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api.getDocument(documentId).then(
      (book) => {
        if (!cancelled) setTitle(book.title?.trim() || book.filename);
      },
      () => {},
    );
    api.quizGenerators().then(
      (offered) => {
        if (!cancelled) setDrafting(offered.generators.includes("graph"));
      },
      () => {},
    );
    api.listQuizzes(documentId).then(
      (found) => {
        if (!cancelled) setQuizzes(found);
      },
      (error) => {
        if (!cancelled) setFailure(explain(error, {}, strings));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, documentId, setFailure, strings]);

  // Arriving from "revise next": open that quiz with only its due questions.
  useEffect(() => {
    if (!review) return;
    let cancelled = false;
    api.getQuiz(review).then(
      (quiz) => {
        if (cancelled) return;
        const due = new Set(quiz.answers.filter((a) => a.due).map((a) => a.question_id));
        const questions = quiz.questions.filter((q) => due.has(q.question_id));
        setOpen(questions.length ? { ...quiz, questions } : quiz);
      },
      (error) => {
        if (!cancelled) setFailure(explain(error, {}, strings));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, review, setFailure, strings]);

  // Back from "hear the source": the same quiz, carrying on where it was.
  const resumeQuiz = resume?.quiz;
  const resumeAt = resume?.question ?? 0;
  useEffect(() => {
    if (!resumeQuiz) return;
    let cancelled = false;
    api.getQuiz(resumeQuiz).then(
      (quiz) => {
        if (cancelled) return;
        setStartAt(Math.min(resumeAt, quiz.questions.length));
        setOpen(quiz);
      },
      (error) => {
        if (!cancelled) setFailure(explain(error, {}, strings));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, resumeQuiz, resumeAt, setFailure, strings]);

  async function refresh() {
    setQuizzes(await api.listQuizzes(documentId));
  }

  // While a model drafts, look again now and then. Not announced as it
  // goes: the list says "being drafted" until it is done.
  const waiting = quizzes?.some((quiz) => quiz.status === "generating") ?? false;
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => {
      api.listQuizzes(documentId).then(setQuizzes, () => {});
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [api, documentId, waiting]);

  async function make(forClass: boolean, generator: "cloze" | "graph" = "cloze") {
    if (busy) return;
    setBusy(true);
    try {
      const made = await api.makeQuiz(documentId, forClass, generator);
      setFailure(null);
      await refresh();
      if (made.status === "generating") {
        say(strings.quizGenerating);
        return;
      }
      say(strings.quizMade);
      setOpen(made);
    } catch (error) {
      setFailure(explain(error, { 422: strings.errorNoQuestions }, strings));
    } finally {
      setBusy(false);
    }
  }

  async function openQuiz(quizId: string) {
    try {
      setStartAt(0);
      setOpen(await api.getQuiz(quizId));
    } catch (error) {
      setFailure(explain(error, {}, strings));
    }
  }

  async function remove(quizId: string) {
    try {
      await api.deleteQuiz(quizId);
      say(strings.quizDeleted);
      await refresh();
    } catch (error) {
      setFailure(explain(error, {}, strings));
    }
  }

  const back = async () => {
    setOpen(null);
    await refresh();
  };

  if (open) {
    return open.mine && open.for_class && open.status === "draft" ? (
      <Review quiz={open} onChange={setOpen} onBack={() => void back()} />
    ) : (
      <TakeQuiz
        key={`${open.quiz_id}-${startAt}`}
        quiz={open}
        documentId={documentId}
        startAt={startAt}
        onBack={() => void back()}
      />
    );
  }

  return (
    <div className="account-page">
      <p>
        <Link href={`/library/${encodeURIComponent(documentId)}`}>{strings.backToReader}</Link>
      </p>
      <h1>{strings.practiceHeading(title)}</h1>
      <p className="hint">{strings.practiceHow}</p>
      {notice}
      <div className="notice-actions">
        <button
          className="btn btn-primary"
          type="button"
          aria-busy={busy}
          onClick={() => void make(false)}
        >
          {strings.makeQuiz}
        </button>
        {account?.role === "teacher" ? (
          <button className="btn" type="button" aria-busy={busy} onClick={() => void make(true)}>
            {strings.makeClassQuiz}
          </button>
        ) : null}
        {drafting ? (
          <button
            className="btn"
            type="button"
            aria-busy={busy}
            onClick={() => void make(false, "graph")}
          >
            {strings.makeDraftedQuiz}
          </button>
        ) : null}
      </div>
      {drafting ? <p className="hint">{strings.draftedHow}</p> : null}

      <section className="account-section card" aria-labelledby="quizzes-heading">
        <h2 id="quizzes-heading">{strings.quizzesHeading}</h2>
        {quizzes === null ? (
          <p className="hint" aria-busy="true">
            {strings.pageLoading}
          </p>
        ) : quizzes.length === 0 ? (
          <p>{strings.noQuizzes}</p>
        ) : (
          <ul className="class-list">
            {quizzes.map((quiz) => {
              const name = strings.quizName(quiz.question_count, quiz.for_class);
              const draft = quiz.mine && quiz.status === "draft";
              return (
                <li key={quiz.quiz_id} className="class-item">
                  <h3>{name}</h3>
                  {quiz.generator === "graph" ? (
                    <p className="hint">{strings.quizDraftedLabel}</p>
                  ) : null}
                  {draft ? <p className="hint">{strings.quizDraft}</p> : null}
                  {quiz.status === "generating" ? (
                    <p className="hint">{strings.quizGenerating}</p>
                  ) : null}
                  {quiz.status === "failed" ? (
                    <>
                      <p className="notice notice-warn">{strings.quizFailed}</p>
                      <div className="notice-actions">
                        <button
                          className="btn btn-sm"
                          type="button"
                          onClick={() => void make(quiz.for_class)}
                        >
                          {strings.makeQuiz}
                        </button>
                      </div>
                    </>
                  ) : null}
                  {quiz.stale ? <p className="hint">{strings.quizStale}</p> : null}
                  <div className="notice-actions">
                    {quiz.question_count > 0 ? (
                      <button
                        className="btn btn-primary btn-sm"
                        type="button"
                        onClick={() => void openQuiz(quiz.quiz_id)}
                      >
                        {draft ? strings.reviewQuiz : strings.startQuiz}
                        <span className="visually-hidden"> — {name}</span>
                      </button>
                    ) : null}
                    {quiz.mine ? (
                      <button
                        className="btn btn-quiet btn-sm"
                        type="button"
                        onClick={() => void remove(quiz.quiz_id)}
                      >
                        {strings.deleteQuiz}
                        <span className="visually-hidden"> — {name}</span>
                      </button>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

/** The question, with its blank spoken as a word rather than as underscores. */
function Question({ text }: { text: string }) {
  const strings = useStrings();
  const [before, ...rest] = text.split(BLANK);
  return (
    <>
      <span lang="si">{before}</span>
      {rest.length > 0 ? (
        <>
          <span aria-hidden="true">{BLANK}</span>
          <span className="visually-hidden">{strings.blankWord}</span>
          <span lang="si">{rest.join(BLANK)}</span>
        </>
      ) : null}
    </>
  );
}

function TakeQuiz({
  quiz,
  documentId,
  startAt,
  onBack,
}: {
  quiz: QuizDetail;
  documentId: string;
  /** Resuming: the questions before this one were answered already. */
  startAt: number;
  onBack: () => void;
}) {
  const strings = useStrings();
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [index, setIndex] = useState(startAt);
  const [choice, setChoice] = useState<number | null>(null);
  const [result, setResult] = useState<AnswerResult | null>(null);
  // Resuming, the score so far is the saved answers to the questions before.
  const [right, setRight] = useState(() => {
    const before = new Set(quiz.questions.slice(0, startAt).map((q) => q.question_id));
    return quiz.answers.filter((a) => before.has(a.question_id) && a.correct).length;
  });
  const [finished, setFinished] = useState(startAt >= quiz.questions.length);
  const [attempts, setAttempts] = useState<QuizAttempt[]>(() => {
    const before = new Set(quiz.questions.slice(0, startAt).map((q) => q.question_id));
    return quiz.answers
      .filter((a) => before.has(a.question_id))
      .map((a) => {
        const question = quiz.questions.find((q) => q.question_id === a.question_id);
        return {
          question_id: a.question_id,
          choice: a.choice,
          correct: a.correct,
          segment_id: question?.segment_id ?? null,
        };
      });
  });
  const heading = useRef<HTMLHeadingElement>(null);
  const nextButton = useRef<HTMLButtonElement>(null);
  const name = useId();

  useEffect(() => {
    heading.current?.focus();
  }, [index, finished]);

  // Check is replaced by the result and the next step, and focus would go
  // with it to <body>. The result has been said; "next" is where focus waits,
  // with "hear the source" and "report" just before it.
  useEffect(() => {
    if (result) nextButton.current?.focus();
  }, [result]);

  const question = quiz.questions[index];
  const total = quiz.questions.length;

  async function check(event: FormEvent) {
    event.preventDefault();
    if (!question || result) return;
    if (choice === null) return setFailure(strings.chooseAnswer);
    try {
      const checked = await api.answerQuiz(quiz.quiz_id, question.question_id, choice);
      setFailure(null);
      setResult(checked);
      if (checked.correct) setRight((count) => count + 1);
      setAttempts((rows) => [
        ...rows.filter((row) => row.question_id !== question.question_id),
        {
          question_id: question.question_id,
          choice,
          correct: checked.correct,
          segment_id: checked.segment_id ?? question.segment_id ?? null,
        },
      ]);
      const answer = question.options[checked.answer] ?? "";
      say(checked.correct ? strings.rightAnswer : strings.wrongAnswer(answer));
    } catch (error) {
      setFailure(explain(error, {}, strings));
    }
  }

  function next() {
    if (index + 1 >= total) {
      setFinished(true);
      return;
    }
    setIndex(index + 1);
    setChoice(null);
    setResult(null);
  }

  if (finished || !question) {
    const byId = new Map(attempts.map((row) => [row.question_id, row]));
    return (
      <div className="account-page">
        <h1 ref={heading} tabIndex={-1}>
          {strings.quizScore(right, total)}
        </h1>
        <table className="data-table">
          <caption>{strings.quizResultsCaption}</caption>
          <thead>
            <tr>
              <th scope="col" className="visually-hidden">
                #
              </th>
              <th scope="col">{strings.quizResultsColQuestion}</th>
              <th scope="col">{strings.quizResultsColOutcome}</th>
              <th scope="col">{strings.hearQuestion}</th>
            </tr>
          </thead>
          <tbody>
            {quiz.questions.map((item, position) => {
              const row = byId.get(item.question_id);
              const segmentId = row?.segment_id ?? item.segment_id;
              return (
                <tr key={item.question_id}>
                  <td className="latin">{position + 1}</td>
                  <td lang="si">
                    <Question text={item.question} />
                  </td>
                  <td>{row ? (row.correct ? strings.quizResultRight : strings.quizResultWrong) : "—"}</td>
                  <td>
                    {segmentId ? (
                      <Link
                        className="btn btn-quiet btn-sm"
                        href={`/library/${encodeURIComponent(documentId)}?segment=${encodeURIComponent(segmentId)}`}
                      >
                        {strings.hearQuestion}
                      </Link>
                    ) : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <button className="btn btn-primary" type="button" onClick={onBack}>
          {strings.backToQuizzes}
        </button>
      </div>
    );
  }

  return (
    <div className="account-page">
      <p>
        <button className="btn btn-quiet btn-sm" type="button" onClick={onBack}>
          {strings.backToQuizzes}
        </button>
      </p>
      <h1 ref={heading} tabIndex={-1}>
        {strings.questionOf(index + 1, total)}
      </h1>
      {quiz.stale ? <p className="hint">{strings.quizStale}</p> : null}
      {notice}
      <form className="account-section card" onSubmit={check} noValidate>
        <fieldset className="decision">
          <legend>
            <Question text={question.question} />
          </legend>
          {question.options.map((option, position) => (
            <label key={option} className="check-row">
              <input
                type="radio"
                name={name}
                checked={choice === position}
                disabled={result !== null}
                onChange={() => setChoice(position)}
              />
              <span lang="si">{option}</span>
            </label>
          ))}
        </fieldset>
        {result ? (
          <>
            <p className={result.correct ? RESULT.right : RESULT.wrong}>
              {result.correct ? (
                strings.rightAnswer
              ) : (
                <Quoted format={strings.wrongAnswer} text={question.options[result.answer] ?? ""} />
              )}
            </p>
            <div className="notice-actions">
              {result.segment_id ? (
                <Link
                  className="btn"
                  // `quiz` and `question` bring the reader back here, to the
                  // next question, from the book (plan section 8.7).
                  href={`/library/${encodeURIComponent(documentId)}?segment=${encodeURIComponent(result.segment_id)}&quiz=${encodeURIComponent(quiz.quiz_id)}&question=${index + 1}`}
                >
                  {strings.hearSource}
                </Link>
              ) : null}
              <Link
                className="btn btn-quiet"
                href={`/report?kind=question&document=${encodeURIComponent(documentId)}&quiz=${encodeURIComponent(quiz.quiz_id)}&question=${encodeURIComponent(question.question_id)}`}
              >
                {strings.reportQuestionLink}
              </Link>
              <button ref={nextButton} className="btn btn-primary" type="button" onClick={next}>
                {index + 1 >= total ? strings.finishQuiz : strings.nextQuestion}
              </button>
            </div>
          </>
        ) : (
          <button className="btn btn-primary" type="submit">
            {strings.checkAnswer}
          </button>
        )}
      </form>
    </div>
  );
}

function Review({
  quiz,
  onChange,
  onBack,
}: {
  quiz: QuizDetail;
  onChange: (quiz: QuizDetail) => void;
  onBack: () => void;
}) {
  const strings = useStrings();
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();

  async function act(work: () => Promise<QuizDetail>, said: string) {
    try {
      onChange(await work());
      say(said);
    } catch (error) {
      setFailure(explain(error, {}, strings));
    }
  }

  return (
    <div className="account-page">
      <p>
        <button className="btn btn-quiet btn-sm" type="button" onClick={onBack}>
          {strings.backToQuizzes}
        </button>
      </p>
      <h1>{strings.reviewQuiz}</h1>
      <p>{strings.quizReviewIntro}</p>
      {notice}
      <ol className="class-list">
        {quiz.questions.map((question, position) => (
          <li key={question.question_id} className="class-item">
            <p>
              <Question text={question.question} />
            </p>
            <p className="hint">
              <Quoted
                format={strings.correctIs}
                text={question.options[question.answer ?? 0] ?? ""}
              />
            </p>
            <button
              className="btn btn-quiet btn-sm"
              type="button"
              onClick={() =>
                void act(
                  () => api.dropQuestion(quiz.quiz_id, question.question_id),
                  strings.questionRemoved,
                )
              }
            >
              {strings.removeQuestion(position + 1)}
            </button>
          </li>
        ))}
      </ol>
      <button
        className="btn btn-primary"
        type="button"
        disabled={quiz.questions.length === 0}
        onClick={() => void act(() => api.publishQuiz(quiz.quiz_id), strings.quizPublished)}
      >
        {strings.publishQuiz}
      </button>
    </div>
  );
}
