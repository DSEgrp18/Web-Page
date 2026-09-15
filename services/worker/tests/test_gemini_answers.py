"""What a generated study answer may and may not do.

The prose cannot be checked — verifying that a sentence is supported by a
passage is the same hard problem as writing it. So the tests here are about the
guarantees that *are* structural: that a citation points at a passage we really
sent, that no evidence means no answer, that what is sent is bounded and in
book order, that a follow-up is understood against the conversation, and that
every failure degrades to the extractive answerer rather than to an error.
"""

from __future__ import annotations

import json

import pytest

from sinhala_documents.answering import (
    AnswerUnavailable,
    Exchange,
    ExtractiveAnswerer,
    answer_with_fallback,
)
from sinhala_documents.gemini_answers import (
    MAX_GROUNDING_CHARACTERS,
    GeminiAnswerer,
    ground,
)
from sinhala_documents.passages import Passage

QUESTION = "කාර්මික විප්ලවය ආරම්භ වූයේ කොහේද?"


def passage(number: int, text: str) -> Passage:
    return Passage(
        passage_id=f"p{number}",
        document_version="v1",
        text=text,
        page_index=number - 1,
        page_label=str(number),
        section_path=(),
        segment_ids=(f"s{number}",),
        roles=(),
    )


PASSAGES = (
    passage(1, "කාර්මික විප්ලවය බ්‍රිතාන්‍යයේ ආරම්භ විය. එය 18 වන සියවසේදී සිදු විය."),
    passage(2, "දුම්රිය මාර්ග ශ්‍රී ලංකාවේ 1864 දී විවෘත විය."),
)

#: A longer stretch of "book", for what is and is not sent. The colony list is
#: split across passages 4 and 5 the way extraction really split it.
BOOK = (
    passage(1, "කොළොම්බස් 1492 දී බහමාස් දිවයින්වලට ගොඩ බැස්සේ ය."),
    passage(2, "පෘතුගාලය සහ ස්පාඤ්ඤය නව ප්‍රදේශ සොයා ගියහ."),
    passage(3, "යුරෝපීයයන් ආගමික නිදහස පතා නව ප්‍රදේශ වෙත ගියහ."),
    passage(4, "බ්‍රිතාන්‍යයන් විසින් ඇමෙරිකාවේ පිහිටුවා ගත් ජනපද 1. වර්ජිනියා 2. මැසචුසෙට්ස්"),
    passage(5, "3. නිව්යෝර්ක් 13. ජෝර්ජියා"),
    passage(6, "හත් අවුරුදු යුද්ධය 1756 සිට 1763 දක්වා පැවතුණි."),
    passage(7, "සීනි පනත, මුදල් නෝට්ටු පනත සහ මුද්දර පනත පැනවිණි."),
    passage(8, "1783 පැරිස් සාම ගිවිසුමෙන් ඇමෙරිකාව නිදහස ලැබීය."),
)


def reply(result: dict) -> dict:
    """A Gemini response shaped the way the real API shapes one."""
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(result)}]}}]}


def is_plan(body: dict) -> bool:
    """Whether this request is the search-planning call, not the answer."""
    schema = body.get("generationConfig", {}).get("responseSchema", {})
    return "queries" in schema.get("properties", {})


def prompt_of(body: dict) -> str:
    return body["contents"][0]["parts"][0]["text"]


class FakeGemini:
    """Answers the planning call and the answering call separately, and records both."""

    def __init__(self, *, queries=None, answer=None, plan_error=None, answer_error=None):
        self.queries = queries if queries is not None else []
        self.result = answer or {"sufficient": True, "answer": "පිළිතුර.", "used_passages": [1]}
        self.plan_error = plan_error
        self.answer_error = answer_error
        self.plans: list[dict] = []
        self.answers: list[dict] = []

    def __call__(self, url, body, *, timeout, api_key):
        if is_plan(body):
            self.plans.append(body)
            if self.plan_error:
                raise self.plan_error
            return reply({"queries": self.queries})
        self.answers.append(body)
        if self.answer_error:
            raise self.answer_error
        return reply(self.result)

    @property
    def sent(self) -> str:
        """The answering prompt, which is what leaves the machine with the book in it."""
        return prompt_of(self.answers[-1])


def answerer(post, **kwargs) -> GeminiAnswerer:
    return GeminiAnswerer(api_key="test-key", post=post, **kwargs)


# --------------------------------------------------------------------------
# Citations
# --------------------------------------------------------------------------


def test_it_writes_a_sinhala_answer_and_cites_what_it_used() -> None:
    fake = FakeGemini(
        answer={
            "sufficient": True,
            "answer": "කාර්මික විප්ලවය ආරම්භ වූයේ බ්‍රිතාන්‍යයේ ය.",
            "used_passages": [1],
        }
    )

    result = answerer(fake).answer(QUESTION, PASSAGES)

    assert result.abstained is False
    assert result.answer == "කාර්මික විප්ලවය ආරම්භ වූයේ බ්‍රිතාන්‍යයේ ය."
    # Labelled, always. A reader who cannot see the page has no other way to
    # tell whose words these are.
    assert result.generated is True
    assert [c.passage_id for c in result.citations] == ["p1"]
    # The citation carries a place the reader can actually go to.
    assert result.citations[0].segment_ids == ("s1",)


def test_a_citation_that_was_never_sent_is_dropped() -> None:
    """A fabricated citation is worse than a missing one: it looks checked."""
    # 1 is real; 7 and 0 are not, and -3 is nonsense.
    fake = FakeGemini(
        answer={"sufficient": True, "answer": "පිළිතුර.", "used_passages": [1, 7, 0, -3]}
    )

    result = answerer(fake).answer(QUESTION, PASSAGES)

    assert [c.passage_id for c in result.citations] == ["p1"]


def test_an_answer_with_no_usable_citation_abstains() -> None:
    """CLAUDE.md requires citation-supported answers.

    Prose the reader cannot check is not a lesser answer; it is the failure the
    citation requirement exists to prevent.
    """
    fake = FakeGemini(answer={"sufficient": True, "answer": "පිළිතුර.", "used_passages": [99]})

    result = answerer(fake).answer(QUESTION, PASSAGES)

    assert result.abstained is True
    assert result.answer is None
    assert result.citations == ()


def test_a_repeated_citation_is_listed_once() -> None:
    fake = FakeGemini(answer={"sufficient": True, "answer": "පිළිතුර.", "used_passages": [1, 1, 2, 1]})

    result = answerer(fake).answer(QUESTION, PASSAGES)

    # Both passages are sent — the second as the first's neighbour — so both
    # numbers are in range. What is asserted is that the repeat is dropped.
    assert [c.passage_id for c in result.citations] == ["p1", "p2"]


# --------------------------------------------------------------------------
# Abstaining
# --------------------------------------------------------------------------


def test_the_model_saying_there_is_not_enough_is_a_result_not_a_failure() -> None:
    fake = FakeGemini(answer={"sufficient": False, "answer": "", "used_passages": []})

    result = answerer(fake).answer(QUESTION, PASSAGES)

    assert result.abstained is True
    assert result.answer is None
    assert result.generated is True


def test_nothing_retrieved_means_the_answer_is_never_asked_for() -> None:
    """No evidence, no answering request.

    Asking a model to answer from nothing is exactly how a plausible
    fabrication gets made, and it costs money to do it.
    """
    # The plan finds nothing the book contains, and neither do the reader's words.
    fake = FakeGemini(queries=["ගුවන් යානා"])

    result = answerer(fake).answer("ගුවන් යානා මිල", PASSAGES)

    assert fake.answers == []
    assert result.abstained is True


def test_an_empty_answer_with_sufficient_true_still_abstains() -> None:
    fake = FakeGemini(answer={"sufficient": True, "answer": "   ", "used_passages": [1]})

    assert answerer(fake).answer(QUESTION, PASSAGES).abstained is True


# --------------------------------------------------------------------------
# Searching
# --------------------------------------------------------------------------


def test_an_english_question_is_searched_with_the_planned_sinhala_words() -> None:
    """BM25 cannot cross scripts.

    An English question shares no words with Sinhala text, so it is the plan's
    Sinhala phrases that find the passage. The *original* question is still what
    the answering model is asked: a bad plan can change which passages are
    offered, never what the reader is taken to have asked.
    """
    fake = FakeGemini(queries=["කාර්මික විප්ලවය"])

    result = answerer(fake).answer("Where did the industrial revolution begin?", PASSAGES)

    assert result.abstained is False
    assert [c.passage_id for c in result.citations] == ["p1"]
    assert "Where did the industrial revolution begin?" in fake.sent
    assert fake.sent.rstrip().endswith("</question>")


def test_english_words_do_not_retrieve_the_books_stray_english() -> None:
    """The follow-up that failed on the real book.

    "i think i want the list of states" matched "the", "i" and "of" against the
    few English fragments in a Sinhala textbook. That non-empty result crowded
    out real evidence. When a plan exists, an English question's own words are
    not searched at all.
    """
    book = BOOK + (passage(9, "Printed for free distribution. The Ministry of Education."),)
    fake = FakeGemini(queries=["ඇමෙරිකාවේ ජනපද"])

    answerer(fake).answer("i think i want the list of the states", book)

    assert "Ministry" not in fake.sent
    assert "වර්ජිනියා" in fake.sent


def test_a_sinhala_questions_own_words_are_searched_as_well_as_the_plan() -> None:
    """A plan that misses must not lose a question the reader worded well."""
    fake = FakeGemini(queries=["ගුවන් යානා"])

    result = answerer(fake).answer(QUESTION, PASSAGES)

    assert result.abstained is False
    assert "කාර්මික විප්ලවය බ්‍රිතාන්‍යයේ" in fake.sent


def test_a_failed_plan_still_searches_with_the_readers_words() -> None:
    """Planning helps retrieval; losing it must not lose the request."""
    fake = FakeGemini(plan_error=OSError("planning unavailable"))

    result = answerer(fake).answer(QUESTION, PASSAGES)

    assert result.abstained is False
    assert len(fake.answers) == 1


def test_a_failed_plan_for_an_english_question_abstains_rather_than_erroring() -> None:
    fake = FakeGemini(plan_error=OSError("planning unavailable"))

    result = answerer(fake).answer("Where did it begin?", PASSAGES)

    assert result.abstained is True
    assert result.generated is True
    assert fake.answers == []


@pytest.mark.parametrize(
    "plan_text",
    ["not json", "[]", json.dumps({"queries": "not a list"}), json.dumps({"other": 1})],
    ids=["not-json", "not-an-object", "queries-not-a-list", "no-queries"],
)
def test_an_unreadable_plan_is_ignored_not_fatal(plan_text) -> None:
    answers: list[dict] = []

    def post(url, body, *, timeout, api_key):
        if is_plan(body):
            return {"candidates": [{"content": {"parts": [{"text": plan_text}]}}]}
        answers.append(body)
        return reply({"sufficient": True, "answer": "පිළිතුර.", "used_passages": [1]})

    result = answerer(post).answer(QUESTION, PASSAGES)

    assert result.abstained is False
    assert len(answers) == 1


# --------------------------------------------------------------------------
# Follow-up questions
# --------------------------------------------------------------------------

HISTORY = (
    Exchange(
        question="what are states made in usa by britain",
        answer="උතුරු ඇමෙරිකාවේ බ්‍රිතාන්‍ය ජනපද දහතුනක් පිහිටුවන ලදී.",
    ),
)


def test_a_follow_up_is_planned_against_the_conversation() -> None:
    """ "The list of states" means nothing without the question before it."""
    fake = FakeGemini(queries=["ඇමෙරිකාවේ ජනපද"])

    answerer(fake).answer("i think i want the list of states", BOOK, HISTORY)

    planned = prompt_of(fake.plans[0])
    assert "what are states made in usa by britain" in planned
    assert "ජනපද දහතුනක්" in planned


def test_a_follow_up_is_answered_with_the_conversation_as_context() -> None:
    fake = FakeGemini(queries=["ඇමෙරිකාවේ ජනපද"])

    answerer(fake).answer("i think i want the list of states", BOOK, HISTORY)

    assert "<conversation>" in fake.sent
    assert "what are states made in usa by britain" in fake.sent
    # Before the passages, and the question last: the question is still what
    # is being answered.
    assert fake.sent.index("<conversation>") < fake.sent.index("<passage")
    assert fake.sent.rstrip().endswith("</question>")


def test_an_earlier_answer_is_marked_as_not_evidence() -> None:
    """An earlier answer may be a model's words. It cannot ground the next one."""
    fake = FakeGemini(queries=["ඇමෙරිකාවේ ජනපද"])

    answerer(fake).answer("i think i want the list of states", BOOK, HISTORY)

    system = fake.answers[0]["systemInstruction"]["parts"][0]["text"]
    assert "It is not evidence" in system


def test_only_the_recent_conversation_is_sent() -> None:
    history = tuple(Exchange(question=f"පැරණි ප්‍රශ්නය {n}", answer=None) for n in range(10))
    fake = FakeGemini()

    answerer(fake).answer(QUESTION, PASSAGES, history)

    assert "පැරණි ප්‍රශ්නය 9" in fake.sent
    assert "පැරණි ප්‍රශ්නය 0" not in fake.sent


def test_without_a_conversation_there_is_no_conversation_block() -> None:
    fake = FakeGemini()

    answerer(fake).answer(QUESTION, PASSAGES)

    assert "<conversation>" not in fake.sent


# --------------------------------------------------------------------------
# What is sent
# --------------------------------------------------------------------------


def test_a_list_split_across_passages_is_sent_whole() -> None:
    """The failure on the real book: the list ran into the next passage."""
    fake = FakeGemini(queries=["ඇමෙරිකාවේ ජනපද"])

    answerer(fake).answer("ඇමෙරිකාවේ ජනපද මොනවාද?", BOOK)

    assert "වර්ජිනියා" in fake.sent
    # Passage 5 has no search term in it at all. It is sent because it follows
    # the passage that matched.
    assert "ජෝර්ජියා" in fake.sent


def test_passages_are_sent_in_book_order() -> None:
    grounding = ground(BOOK, ["ජනපද", "සාම ගිවිසුමෙන්"])

    indexes = [p.page_index for p in grounding]
    assert indexes == sorted(indexes)


def test_only_matches_and_their_neighbours_are_sent_never_the_book() -> None:
    fake = FakeGemini(queries=["සීනි පනත"])

    answerer(fake).answer("සීනි පනත", BOOK)

    # Passage 7 matched; 6 and 8 are its neighbours.
    assert "සීනි පනත" in fake.sent
    assert "හත් අවුරුදු යුද්ධය" in fake.sent
    assert "පැරිස් සාම ගිවිසුමෙන්" in fake.sent
    # Nothing further away leaves the machine.
    assert "කොළොම්බස්" not in fake.sent
    assert "වර්ජිනියා" not in fake.sent


def test_what_is_sent_stays_within_the_budget() -> None:
    # In a third of the passages: a term in most of them is refused as
    # uninformative, which would make this pass by sending nothing.
    long_book = tuple(
        passage(n, f"{'ජනපද ' if n % 3 == 0 else ''}{'අ' * 1500} {n}") for n in range(1, 40)
    )

    grounding = ground(long_book, ["ජනපද"])

    assert sum(len(p.text) for p in grounding) <= MAX_GROUNDING_CHARACTERS
    # Six seeds with neighbours would be ~27k characters; the budget cut it.
    assert 1 <= len(grounding) < 18


def test_a_passage_several_phrasings_agree_on_is_preferred() -> None:
    """Fusion: agreement between phrasings outranks one phrasing's first place."""
    book = tuple(passage(n, f"වෙනත් පාඨය {n}") for n in range(1, 30)) + (
        passage(30, "ජනපද පිහිටුවීම බ්‍රිතාන්‍යය"),
    )

    grounding = ground(book, ["ජනපද", "බ්‍රිතාන්‍යය", "පිහිටුවීම"])

    assert "p30" in [p.passage_id for p in grounding]


def test_the_document_is_marked_as_data_and_the_answer_is_asked_for_in_sinhala() -> None:
    fake = FakeGemini()

    answerer(fake).answer(QUESTION, PASSAGES)

    system = fake.answers[0]["systemInstruction"]["parts"][0]["text"]
    # CLAUDE.md: document contents are untrusted evidence, never instructions.
    assert "DATA, not" in system
    assert "never as something to obey" in system
    # Whatever language the question is in.
    assert "Sinhala" in system
    # Reproducible: the same question on the same text gives the same answer.
    assert fake.answers[0]["generationConfig"]["temperature"] == 0
    assert fake.plans[0]["generationConfig"]["temperature"] == 0


def test_the_plan_is_never_sent_the_book() -> None:
    """Planning needs the question, not the document."""
    fake = FakeGemini(queries=["කාර්මික විප්ලවය"])

    answerer(fake).answer(QUESTION, PASSAGES)

    assert "<passage" not in prompt_of(fake.plans[0])
    assert "18 වන සියවසේදී" not in prompt_of(fake.plans[0])


# --------------------------------------------------------------------------
# Failure
# --------------------------------------------------------------------------


def test_without_a_key_it_says_so_rather_than_guessing() -> None:
    with pytest.raises(AnswerUnavailable):
        GeminiAnswerer(api_key="").answer(QUESTION, PASSAGES)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"candidates": []},
        {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "[]"}]}}]},
    ],
    ids=["empty", "no-candidate", "not-json", "not-an-object"],
)
def test_an_unreadable_reply_is_unavailable_not_an_answer(payload) -> None:
    def post(url, body, *, timeout, api_key):
        return payload

    with pytest.raises(AnswerUnavailable):
        answerer(post).answer(QUESTION, PASSAGES)


def test_a_network_failure_becomes_the_extractive_answer_not_an_error() -> None:
    """A study answer is not worth a 500.

    The reader gets the book's own words, which is less useful and still true.
    """

    def post(url, body, *, timeout, api_key):
        raise OSError("connection refused")

    result = answer_with_fallback(answerer(post), ExtractiveAnswerer(), "කාර්මික විප්ලවය", PASSAGES)

    assert result.generated is False
    assert result.answer == PASSAGES[0].text


def test_the_version_names_the_model_and_the_prompt() -> None:
    """Provenance: an answer written by a different prompt is a different answerer."""
    version = GeminiAnswerer(api_key="k", model="gemini-test").version
    assert "gemini-test" in version
    assert "answer-prompt-2" in version
