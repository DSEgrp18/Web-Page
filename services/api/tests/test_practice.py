"""Practice quizzes: made from the book, checked by the verifier, seen by the
right people only."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from conftest import later_lesson_page, legacy_page, lesson_page
from test_publishing import School, cheap_hashing, sessions_auth  # noqa: F401


@pytest.fixture
def school() -> School:
    return School()


def make(school: School, doc: str, who, **body):
    return school.client.post(f"/documents/{doc}/quizzes", json=body, headers=who)


class TestAPersonalQuiz:
    def test_is_made_from_the_books_own_sentences(self, school: School) -> None:
        doc = school.upload([lesson_page()])

        made = make(school, doc, school.teacher)

        assert made.status_code == 201, made.text
        quiz = made.json()
        assert quiz["status"] == "published" and quiz["generator"] == "cloze"
        assert quiz["questions"] and quiz["stale"] is False
        stored = school.store.quiz_for(quiz["quiz_id"], school.teacher_id)
        assert stored is not None
        provenance = json.loads(stored.provenance)
        assert provenance["verifier_version"] and provenance["generator"] == "cloze"

    def test_an_answer_is_checked_and_points_at_the_source(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        quiz = make(school, doc, school.teacher).json()
        question = quiz["questions"][0]
        right = question["answer"]

        result = school.client.post(
            f"/quizzes/{quiz['quiz_id']}/answers",
            json={"question_id": question["question_id"], "choice": right},
            headers=school.teacher,
        ).json()

        assert result["correct"] is True
        assert result["segment_id"] and result["quote"]
        again = school.client.get(f"/quizzes/{quiz['quiz_id']}", headers=school.teacher).json()
        assert again["answers"] == [
            {"question_id": question["question_id"], "choice": right, "correct": True, "due": False}
        ]

    def test_is_nobody_elses(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)
        quiz = make(school, doc, school.teacher).json()

        assert (
            school.client.get(f"/quizzes/{quiz['quiz_id']}", headers=school.student).status_code
            == 404
        )
        listed = school.client.get(f"/documents/{doc}/quizzes", headers=school.student).json()
        assert listed == []

    def test_a_class_member_can_make_their_own(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)

        made = make(school, doc, school.student)

        assert made.status_code == 201
        assert made.json()["questions"][0]["answer"] is not None  # theirs, so theirs to see

    def test_a_stranger_cannot_make_one(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        assert make(school, doc, school.student).status_code == 404

    def test_goes_stale_when_the_book_changes(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        quiz = make(school, doc, school.teacher).json()
        document = school.store.get_document(doc, school.teacher_id)
        assert document is not None
        school.store.put_document(replace(document, version="v-new"))

        again = school.client.get(f"/quizzes/{quiz['quiz_id']}", headers=school.teacher).json()
        assert again["stale"] is True


class TestAClassQuiz:
    def test_reaches_the_class_only_once_the_teacher_publishes_it(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)
        quiz = make(school, doc, school.teacher, for_class=True).json()
        url = f"/quizzes/{quiz['quiz_id']}"

        assert quiz["status"] == "draft"
        assert school.client.get(url, headers=school.student).status_code == 404

        published = school.client.post(f"{url}/publish", headers=school.teacher).json()
        seen = school.client.get(url, headers=school.student).json()

        assert published["status"] == "published"
        assert seen["questions"] and all(q["answer"] is None for q in seen["questions"])
        kinds = [e.kind for e in school.store.audit_for(school.teacher_id)]
        assert "quiz_published" in kinds

    def test_the_teacher_removes_questions_in_review(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        quiz = make(school, doc, school.teacher, for_class=True).json()
        first = quiz["questions"][0]["question_id"]

        left = school.client.delete(
            f"/quizzes/{quiz['quiz_id']}/questions/{first}", headers=school.teacher
        ).json()

        assert first not in [q["question_id"] for q in left["questions"]]

    def test_only_the_books_teacher_makes_one(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)

        refused = make(school, doc, school.student, for_class=True)

        assert refused.status_code == 403

    def test_a_removed_student_loses_it(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        school.publish(doc)
        quiz = make(school, doc, school.teacher, for_class=True).json()
        school.client.post(f"/quizzes/{quiz['quiz_id']}/publish", headers=school.teacher)
        school.client.post(
            f"/classes/{school.class_id}/members/{school.student_id}/remove",
            headers=school.teacher,
        )

        seen = school.client.get(f"/quizzes/{quiz['quiz_id']}", headers=school.student)

        assert seen.status_code == 404


class TestWhatGroundsAQuestion:
    def test_never_a_page_that_needs_review(self, school: School) -> None:
        # The first page reads cleanly; the second only through OCR, undecided.
        doc = school.upload([lesson_page(), legacy_page("DL-Manel")])
        flagged = school.client.get(f"/documents/{doc}/review", headers=school.teacher).json()
        assert [p["page_index"] for p in flagged["pages"]] == [1]

        quiz = make(school, doc, school.teacher).json()
        stored = school.store.quiz_for(quiz["quiz_id"], school.teacher_id)
        assert stored is not None

        assert {q["page_index"] for q in json.loads(stored.questions)} == {0}

    def test_the_model_generator_is_refused_where_it_is_off(self, school: School) -> None:
        doc = school.upload([lesson_page()])

        refused = make(school, doc, school.teacher, generator="graph")

        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "generator_unavailable"


class TestDisclosure:
    """The privacy notice reads ``/readiness`` to say whether practice
    questions can leave the server; it must say so exactly when they can."""

    def test_readiness_says_questions_stay_here_by_default(
        self, school: School, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SINHALA_READER_QUIZ", raising=False)
        assert school.client.get("/readiness").json()["quiz"] == "local"

    def test_readiness_says_questions_go_to_google_when_drafting_is_on(
        self, school: School, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SINHALA_READER_QUIZ", "graph")
        assert school.client.get("/readiness").json()["quiz"] == "gemini"


class TestDeletion:
    def test_deleting_the_book_takes_its_quizzes(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        quiz = make(school, doc, school.teacher).json()

        school.client.delete(f"/documents/{doc}", headers=school.teacher)

        assert school.store.quiz_for(quiz["quiz_id"], school.teacher_id) is None

    def test_the_maker_deletes_their_quiz(self, school: School) -> None:
        doc = school.upload([lesson_page()])
        quiz = make(school, doc, school.teacher).json()

        gone = school.client.delete(f"/quizzes/{quiz['quiz_id']}", headers=school.teacher)

        assert gone.status_code == 204
        assert school.store.quizzes_for(doc, school.teacher_id) == []


def _fake_model(system: str, user: str) -> dict:
    """Drafts from the passage it is shown, the way a well-behaved model would."""
    if "Answer the multiple-choice question" in system:
        return {"choice": 0}
    body = user.split(">\n", 1)[1].split("\n</passage>", 1)[0]
    quote = body.split(".")[0].strip() + "."
    answer = max(quote.replace(".", "").split(), key=len)
    return {
        "question": quote.replace(answer, "_____", 1),
        "options": [answer, "ඇඇඇඇඇ", "ඉඉඉඉඉ", "උඋඋඋඋ"],
        "answer": 0,
        "quote": quote,
    }


class TestModelDraftedQuestions:
    @pytest.fixture(autouse=True)
    def graph_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pytest.importorskip("langgraph")
        monkeypatch.setenv("SINHALA_READER_QUIZ", "graph")

    def test_are_drafted_verified_and_labelled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from sinhala_documents import quiz_graph

        monkeypatch.setattr(quiz_graph, "gemini_transport", lambda: _fake_model)
        school = School()
        doc = school.upload([lesson_page(), lesson_page()])

        made = make(school, doc, school.teacher, generator="graph")

        assert made.status_code == 202, made.text
        quiz = school.client.get(f"/quizzes/{made.json()['quiz_id']}", headers=school.teacher)
        body = quiz.json()
        assert body["generator"] == "graph"
        stored = school.store.quiz_for(body["quiz_id"], school.teacher_id)
        assert stored is not None
        provenance = json.loads(stored.provenance)
        assert provenance["framework"].startswith("langgraph")
        assert provenance["verifier_version"] and provenance["prompt_version"]
        assert body["status"] == "published", provenance
        assert body["questions"]

    def test_a_provider_failure_fails_the_quiz_and_is_not_swapped_for_cloze(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sinhala_documents import quiz_graph

        def down() -> quiz_graph.Transport:
            raise quiz_graph.ProviderFailure("no key")

        monkeypatch.setattr(quiz_graph, "gemini_transport", down)
        school = School()
        doc = school.upload([lesson_page()])

        made = make(school, doc, school.teacher, generator="graph").json()
        again = school.client.get(f"/quizzes/{made['quiz_id']}", headers=school.teacher).json()

        assert again["status"] == "failed"
        assert again["questions"] == [] and again["generator"] == "graph"

    def test_the_api_will_not_start_it_without_a_queue(self) -> None:
        from sinhala_reader import Deps
        from sinhala_reader.storage import InMemoryStore

        with pytest.raises(RuntimeError, match="SINHALA_READER_QUEUE=celery"):
            Deps(store=InMemoryStore(), warm_on_start=False)

    def test_offers_both_kinds(self) -> None:
        school = School()
        offered = school.client.get("/quiz-generators", headers=school.teacher).json()
        assert offered == {"generators": ["cloze", "graph"]}


def test_the_api_process_never_loads_langgraph() -> None:
    """CLAUDE.md, "The agentic boundary": a fresh API process, configured for
    model-drafted questions, builds its app and serves a quiz route without
    importing the framework. Only the worker does."""
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    script = (
        "import sys, os\n"
        "os.environ.update(SINHALA_READER_QUIZ='graph', SINHALA_READER_QUEUE='celery',"
        " SINHALA_READER_REDIS_URL='redis://127.0.0.1:1/0', SINHALA_READER_AUTH='development')\n"
        "from fastapi.testclient import TestClient\n"
        "from sinhala_reader import Deps, create_app\n"
        "client = TestClient(create_app(Deps(warm_on_start=False, reap_stalled=False)))\n"
        "client.get('/quiz-generators')\n"
        "loaded = [m for m in ('langgraph', 'langchain_core') if m in sys.modules]\n"
        "print(loaded)\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    paths = [root / "src", root.parent / "worker" / "src", root.parent / "tts" / "src"]
    env = {**__import__("os").environ, "PYTHONPATH": __import__("os").pathsep.join(map(str, paths))}
    done = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stdout + done.stderr


class TestWhatTheReaderAskedFor:
    def test_questions_come_only_from_the_pages_chosen(self, school: School) -> None:
        doc = school.upload([lesson_page(), later_lesson_page()])

        made = make(school, doc, school.teacher, first_page=1, last_page=1)

        assert made.status_code == 201, made.text
        stored = school.store.quiz_for(made.json()["quiz_id"], school.teacher_id)
        assert stored is not None
        assert {q["page_index"] for q in json.loads(stored.questions)} == {1}

    def test_the_request_is_kept_and_shown_with_the_quiz(self, school: School) -> None:
        doc = school.upload([lesson_page()])

        made = make(school, doc, school.teacher, topic="  මහාතිත්ථ <වරාය>  ", count=5)

        asked = made.json()["asked"]
        # One line of plain text: brackets could close the model's fence.
        assert asked["topic"] == "මහාතිත්ථ වරාය"
        assert asked["count"] == 5 and asked["kind"] == "mixed"
        assert len(made.json()["questions"]) <= 5
        listed = school.client.get(f"/documents/{doc}/quizzes", headers=school.teacher).json()
        assert listed[0]["asked"]["topic"] == "මහාතිත්ථ වරාය"

    def test_a_page_range_that_runs_backwards_is_refused(self, school: School) -> None:
        doc = school.upload([lesson_page(), lesson_page()])

        refused = make(school, doc, school.teacher, first_page=1, last_page=0)

        assert refused.status_code == 422
        assert refused.json()["detail"]["code"] == "bad_pages"

    def test_nothing_on_the_chosen_pages_is_said_not_papered_over(self, school: School) -> None:
        doc = school.upload([lesson_page()])

        empty = make(school, doc, school.teacher, first_page=5, last_page=9)

        assert empty.status_code == 422
        assert empty.json()["detail"]["code"] == "no_questions"


class TestDrafting:
    """The worker's half, with a fake model: no network."""

    def _quiz(self, school: School, doc: str, **asked) -> str:
        from sinhala_reader.practice import QuizRequest, provenance
        from sinhala_reader.storage import Quiz, QuizStatus, new_id

        reading = school.store.readable_document(doc, school.teacher_id)
        assert reading is not None and reading.document.version
        quiz_id = new_id("quiz")
        school.store.put_quiz(
            Quiz(
                quiz_id=quiz_id,
                document_id=doc,
                creator=school.teacher_id,
                version=reading.document.version,
                for_class=False,
                status=QuizStatus.GENERATING,
                provenance=provenance("graph", request=QuizRequest(**asked).as_dict()),
                questions="[]",
            )
        )
        return quiz_id

    def test_the_model_is_asked_about_the_chosen_pages_and_topic(self, school: School) -> None:
        pytest.importorskip("langgraph")
        from sinhala_reader.practice import draft_quiz

        doc = school.upload([lesson_page(), later_lesson_page()])
        quiz_id = self._quiz(school, doc, first_page=1, last_page=1, topic="වරාය", kind="causes")
        prompts: list[str] = []

        def fake(system: str, user: str) -> dict:
            prompts.append(user)
            return {"nonsense": True}

        draft_quiz(school.store, quiz_id, transport=fake)

        assert prompts
        assert all("<topic>\nවරාය\n</topic>" in p for p in prompts)
        stored = school.store.quiz_for(quiz_id, school.teacher_id)
        assert stored is not None
        assert json.loads(stored.provenance)["request"]["first_page"] == 1

    def test_a_missing_drafter_fails_the_quiz_and_says_so(
        self, school: School, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sinhala_documents import quiz_graph

        from sinhala_reader.practice import draft_quiz
        from sinhala_reader.storage import QuizStatus

        def missing(*_args, **_kwargs):
            raise ModuleNotFoundError("No module named 'langgraph'")

        monkeypatch.setattr(quiz_graph, "draft_questions", missing)
        doc = school.upload([lesson_page()])
        quiz_id = self._quiz(school, doc)

        draft_quiz(school.store, quiz_id, transport=lambda system, user: {})

        stored = school.store.quiz_for(quiz_id, school.teacher_id)
        assert stored is not None and stored.status == QuizStatus.FAILED
        assert "not installed" in json.loads(stored.provenance)["failure"]
