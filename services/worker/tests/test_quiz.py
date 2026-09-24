"""The practice-question verifier and the fill-in-the-blank generator.

The fixture suite of bad candidates is the permanent CI check the product plan
asks for: each must be rejected, with the right code.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from sinhala_documents.passages import Passage
from sinhala_documents.quiz import (
    BLANK,
    Candidate,
    Rejection,
    Sentence,
    SourcePassage,
    cloze_questions,
    normalise,
    verify,
)
from sinhala_documents.retrieval import LexicalIndex

TEXT = "ශ්‍රී ලංකාවේ අගනුවර ශ්‍රී ජයවර්ධනපුර කෝට්ටේ වේ. කොළඹ ප්‍රධාන වරාය නගරයයි."

PASSAGES = {
    1: SourcePassage(1, TEXT, 0, "1", ("s1", "s2")),
    2: SourcePassage(2, "නවතා ඇති පිටුවකි.", 1, "2", ("s3",), accepted=False),
}

GOOD = Candidate(
    question=f"ශ්‍රී ලංකාවේ අගනුවර {BLANK} වේ.",
    options=("ශ්‍රී ජයවර්ධනපුර කෝට්ටේ", "මහනුවර", "ගාල්ල", "යාපනය"),
    answer=0,
    passage=1,
    quote="ශ්‍රී ලංකාවේ අගනුවර ශ්‍රී ජයවර්ධනපුර කෝට්ටේ වේ.",
)


def test_a_grounded_question_passes() -> None:
    assert verify(GOOD, PASSAGES) is None


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"passage": 9}, Rejection.UNKNOWN_PASSAGE),
        ({"passage": 2, "quote": "නවතා ඇති පිටුවකි."}, Rejection.PAGE_NOT_ACCEPTED),
        ({"question": "  "}, Rejection.EMPTY),
        ({"options": ("ශ්‍රී ජයවර්ධනපුර කෝට්ටේ", "මහනුවර", "ගාල්ල")}, Rejection.TOO_FEW_OPTIONS),
        (
            {"options": ("ශ්‍රී ජයවර්ධනපුර කෝට්ටේ", "මහනුවර", "මහනුවර ", "යාපනය")},
            Rejection.OPTIONS_NOT_DISTINCT,
        ),
        ({"answer": 4}, Rejection.BAD_ANSWER_INDEX),
        ({"quote": "ශ්‍රී ලංකාවේ අගනුවර මහනුවර වේ."}, Rejection.QUOTE_NOT_IN_PASSAGE),
        ({"answer": 1}, Rejection.ANSWER_NOT_IN_QUOTE),
        (
            {"options": ("ශ්‍රී ජයවර්ධනපුර කෝට්ටේ", "අගනුවර", "ගාල්ල", "යාපනය")},
            Rejection.DISTRACTOR_IN_QUOTE,
        ),
        (
            {"question": "ශ්‍රී ලංකාවේ අගනුවර ශ්‍රී ජයවර්ධනපුර කෝට්ටේ ද?"},
            Rejection.ANSWER_IN_QUESTION,
        ),
    ],
)
def test_each_bad_candidate_is_rejected_with_its_code(change: dict, code: Rejection) -> None:
    assert verify(replace(GOOD, **change), PASSAGES) is code


def test_a_quote_without_its_joiner_is_not_the_books_words() -> None:
    # ශ්‍රී without the zero-width joiner is a different spelling.
    stripped = GOOD.quote.replace("‍", "")
    assert verify(replace(GOOD, quote=stripped), PASSAGES) is Rejection.QUOTE_NOT_IN_PASSAGE


def test_normalise_keeps_joiners_and_folds_space() -> None:
    assert normalise("ශ්‍රී   ලංකා\n") == "ශ්‍රී ලංකා"
    assert "‍" in normalise("ශ්‍රී")


BOOK = [
    "ගල් යුගයේ මිනිසුන් ගුහාවල ජීවත් වූහ.",
    "කෘෂිකර්මය ආරම්භ වීමෙන් ගම්මාන ඇති විය.",
    "වාරිමාර්ග මගින් වී ගොවිතැන දියුණු කළහ.",
    "පොළොන්නරුව රාජධානිය වැව් රාශියක් ඉදි කළේය.",
    "අනුරාධපුරය පළමු රාජධානිය ලෙස සැලකේ.",
    "සීගිරිය කාශ්‍යප රජුගේ බලකොටුව විය.",
    "දළදා මාළිගාව මහනුවර පිහිටා ඇත.",
    "වෙළඳාම නිසා වරායන් දියුණු විය.",
]


def _book() -> tuple[list[Sentence], LexicalIndex, dict[int, SourcePassage]]:
    passages = [
        Passage(
            passage_id=f"p{i}",
            document_version="v1",
            text=text,
            page_index=i,
            page_label=str(i + 1),
            segment_ids=(f"s{i}",),
        )
        for i, text in enumerate(BOOK)
    ]
    sentences = [Sentence(passage=i + 1, segment_id=f"s{i}", text=t) for i, t in enumerate(BOOK)]
    sources = {
        i + 1: SourcePassage(i + 1, t, i, str(i + 1), (f"s{i}",)) for i, t in enumerate(BOOK)
    }
    return sentences, LexicalIndex(passages), sources


def test_cloze_questions_pass_the_verifier() -> None:
    sentences, index, sources = _book()

    made = cloze_questions(sentences, index, seed="v1", limit=5)

    assert made
    for candidate in made:
        assert verify(candidate, sources) is None, candidate
        assert BLANK in candidate.question
        assert candidate.quote in BOOK


def test_cloze_is_deterministic_for_a_seed() -> None:
    sentences, index, _ = _book()

    assert cloze_questions(sentences, index, seed="v1") == cloze_questions(
        sentences, index, seed="v1"
    )


def test_cloze_blanks_the_books_own_word() -> None:
    sentences, index, _ = _book()

    for candidate in cloze_questions(sentences, index, seed="v1"):
        answer = candidate.options[candidate.answer]
        assert candidate.question.replace(BLANK, answer) == candidate.quote
