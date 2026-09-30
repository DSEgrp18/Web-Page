"""The bounded question-drafting graph, against fake transports: no network."""

from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from sinhala_documents.quiz import SourcePassage, verify  # noqa: E402
from sinhala_documents.quiz_graph import (  # noqa: E402
    BLIND_CHECK_DISAGREES,
    KINDS,
    MAX_CALLS,
    MAX_REVISIONS,
    ProviderFailure,
    calls_for,
    draft_questions,
)

SENTENCE = "ශ්‍රී ලංකාවේ අගනුවර ශ්‍රී ජයවර්ධනපුර කෝට්ටේ වේ."
TEXT = SENTENCE + " කොළඹ ප්‍රධාන වරාය නගරය වන අතර වෙළඳාමේ කේන්ද්‍රස්ථානය ද වේ. " * 2

PASSAGES = [SourcePassage(n, TEXT, n, str(n), (f"s{n}",)) for n in range(1, 9)]

GOOD = {
    "question": "ශ්‍රී ලංකාවේ අගනුවර කුමක්ද?",
    "options": ["ශ්‍රී ජයවර්ධනපුර කෝට්ටේ", "මහනුවර", "ගාල්ල", "යාපනය"],
    "answer": 0,
    "quote": SENTENCE,
}


def transport(draft: dict, choice: int | None = 0):
    calls: list[str] = []

    def send(system: str, user: str) -> dict:
        blind = "Answer the multiple-choice question" in system
        calls.append("blind" if blind else "draft")
        return {"choice": choice} if blind else dict(draft)

    send.calls = calls  # type: ignore[attr-defined]
    return send


def test_accepts_only_what_the_verifier_passes_and_the_model_confirms() -> None:
    result = draft_questions(PASSAGES, transport(GOOD), target=3)

    assert len(result.accepted) == 3
    by_number = {p.number: p for p in PASSAGES}
    assert all(verify(c, by_number) is None for c in result.accepted)


def test_a_rejected_draft_is_redrafted_at_most_twice_then_dropped() -> None:
    bad = {**GOOD, "quote": "පොතේ නැති වාක්‍යයකි."}
    send = transport(bad)

    result = draft_questions(PASSAGES[:1], send, target=1)

    assert result.accepted == []
    assert send.calls == ["draft"] * (MAX_REVISIONS + 1)  # type: ignore[attr-defined]
    assert result.rejections == ["quote_not_in_passage"] * (MAX_REVISIONS + 1)


def test_the_models_opinion_can_reject_but_never_accept() -> None:
    disagrees = draft_questions(PASSAGES[:2], transport(GOOD, choice=1), target=2)
    assert disagrees.accepted == []
    assert BLIND_CHECK_DISAGREES in disagrees.rejections

    # The model agreeing does not rescue a question the verifier rejected.
    wrong = {**GOOD, "options": ["මහනුවර", "ගාල්ල", "යාපනය", "මාතර"]}
    agrees = draft_questions(PASSAGES[:2], transport(wrong, choice=0), target=2)
    assert agrees.accepted == []


def test_never_makes_more_than_its_calls() -> None:
    result = draft_questions(PASSAGES, transport({"nonsense": True}), target=5)

    assert result.calls <= MAX_CALLS
    assert result.accepted == []


def test_stops_at_the_deadline() -> None:
    ticks = iter(range(0, 10_000, 100))

    result = draft_questions(PASSAGES, transport(GOOD), target=5, clock=lambda: next(ticks))

    assert result.stopped == "deadline"
    assert len(result.accepted) < 5


def test_a_provider_failure_is_said_not_hidden() -> None:
    def down(system: str, user: str) -> dict:
        raise ProviderFailure("down")

    with pytest.raises(ProviderFailure):
        draft_questions(PASSAGES, down)


def test_never_drafts_from_a_page_that_is_not_accepted() -> None:
    held = [SourcePassage(1, TEXT, 0, "1", ("s1",), accepted=False)]
    send = transport(GOOD)

    result = draft_questions(held, send)

    assert send.calls == []  # type: ignore[attr-defined]
    assert result.accepted == []


def recording(draft: dict, choice: int = 0):
    """A transport that keeps every prompt it was sent."""
    prompts: list[tuple[str, str]] = []

    def send(system: str, user: str) -> dict:
        prompts.append((system, user))
        blind = "Answer the multiple-choice question" in system
        return {"choice": choice} if blind else dict(draft)

    send.prompts = prompts  # type: ignore[attr-defined]
    return send


def test_drafts_only_from_the_part_the_student_chose() -> None:
    send = recording(GOOD)

    result = draft_questions(PASSAGES, send, target=2, scope={3, 4})

    assert result.accepted
    assert {c.passage for c in result.accepted} <= {3, 4}
    drafts = [user for system, user in send.prompts if "Answer the multiple-choice" not in system]
    assert all('passage number="3"' in u or 'passage number="4"' in u for u in drafts)


def test_the_topic_kind_context_and_lesson_terms_reach_the_model_fenced() -> None:
    send = recording(GOOD)

    draft_questions(
        PASSAGES,
        send,
        target=1,
        kind="causes",
        topic="වරාය නගරය",
        scope={2, 3, 4},
        first=[3],
        lesson_terms=["වෙළඳාම", "කේන්ද්‍රස්ථානය"],
    )

    system, user = send.prompts[0]
    assert "evidence" in system or "never an instruction" in system
    assert 'passage number="3"' in user  # the topic's passage comes first
    assert "<topic>\nවරාය නගරය\n</topic>" in user
    assert "<context>" in user and "<lesson_terms>" in user
    assert KINDS["causes"] in user


def test_context_never_comes_from_outside_the_part_asked_for() -> None:
    send = recording(GOOD)

    draft_questions(PASSAGES, send, target=1, scope={3})

    _system, user = send.prompts[0]
    assert "<context>" not in user


def test_the_budget_grows_with_the_questions_asked_for_but_is_capped() -> None:
    assert calls_for(5) < calls_for(10) < calls_for(15) <= MAX_CALLS
    result = draft_questions(PASSAGES, transport({"nonsense": True}), target=2)
    assert result.calls <= calls_for(2)
