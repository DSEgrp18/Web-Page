"""Practice quizzes: made from the book, checked by the verifier, seen by the
right people only."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from conftest import legacy_page, sinhala_page
from test_publishing import School, cheap_hashing, sessions_auth  # noqa: F401


@pytest.fixture
def school() -> School:
    return School()


def make(school: School, doc: str, who, **body):
    return school.client.post(f"/documents/{doc}/quizzes", json=body, headers=who)


class TestAPersonalQuiz:
    def test_is_made_from_the_books_own_sentences(self, school: School) -> None:
        doc = school.upload([sinhala_page()])

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
        doc = school.upload([sinhala_page()])
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
            {"question_id": question["question_id"], "choice": right, "correct": True}
        ]

    def test_is_nobody_elses(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)
        quiz = make(school, doc, school.teacher).json()

        assert (
            school.client.get(f"/quizzes/{quiz['quiz_id']}", headers=school.student).status_code
            == 404
        )
        listed = school.client.get(f"/documents/{doc}/quizzes", headers=school.student).json()
        assert listed == []

    def test_a_class_member_can_make_their_own(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        made = make(school, doc, school.student)

        assert made.status_code == 201
        assert made.json()["questions"][0]["answer"] is not None  # theirs, so theirs to see

    def test_a_stranger_cannot_make_one(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        assert make(school, doc, school.student).status_code == 404

    def test_goes_stale_when_the_book_changes(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        quiz = make(school, doc, school.teacher).json()
        document = school.store.get_document(doc, school.teacher_id)
        assert document is not None
        school.store.put_document(replace(document, version="v-new"))

        again = school.client.get(f"/quizzes/{quiz['quiz_id']}", headers=school.teacher).json()
        assert again["stale"] is True


class TestAClassQuiz:
    def test_reaches_the_class_only_once_the_teacher_publishes_it(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
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
        doc = school.upload([sinhala_page()])
        quiz = make(school, doc, school.teacher, for_class=True).json()
        first = quiz["questions"][0]["question_id"]

        left = school.client.delete(
            f"/quizzes/{quiz['quiz_id']}/questions/{first}", headers=school.teacher
        ).json()

        assert first not in [q["question_id"] for q in left["questions"]]

    def test_only_the_books_teacher_makes_one(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        school.publish(doc)

        refused = make(school, doc, school.student, for_class=True)

        assert refused.status_code == 403

    def test_a_removed_student_loses_it(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
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
        doc = school.upload([sinhala_page(), legacy_page("DL-Manel")])
        flagged = school.client.get(f"/documents/{doc}/review", headers=school.teacher).json()
        assert [p["page_index"] for p in flagged["pages"]] == [1]

        quiz = make(school, doc, school.teacher).json()
        stored = school.store.quiz_for(quiz["quiz_id"], school.teacher_id)
        assert stored is not None

        assert {q["page_index"] for q in json.loads(stored.questions)} == {0}

    def test_the_model_generator_is_refused_where_it_is_off(self, school: School) -> None:
        doc = school.upload([sinhala_page()])

        refused = make(school, doc, school.teacher, generator="graph")

        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "generator_unavailable"


class TestDeletion:
    def test_deleting_the_book_takes_its_quizzes(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
        quiz = make(school, doc, school.teacher).json()

        school.client.delete(f"/documents/{doc}", headers=school.teacher)

        assert school.store.quiz_for(quiz["quiz_id"], school.teacher_id) is None

    def test_the_maker_deletes_their_quiz(self, school: School) -> None:
        doc = school.upload([sinhala_page()])
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
        doc = school.upload([sinhala_page(), sinhala_page()])

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
        doc = school.upload([sinhala_page()])

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
