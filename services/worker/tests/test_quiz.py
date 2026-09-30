"""The practice-question verifier and the fill-in-the-blank generator.

The fixture suite of bad candidates is the permanent CI check the product plan
asks for: each must be rejected, with the right code.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

import pytest

from sinhala_documents.passages import Passage
from sinhala_documents.quiz import (
    BLANK,
    MIN_OCCURRENCES,
    Candidate,
    Rejection,
    Sentence,
    SourcePassage,
    cloze_questions,
    normalise,
    verify,
)
from sinhala_documents.retrieval import LexicalIndex, tokenize

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


#: A lesson as a textbook writes one: its terms come back. Every word here is
#: used in at least two sentences or is plain grammar, as the generator now
#: requires of a blank and of a distractor (see MIN_OCCURRENCES).
BOOK = [
    "අනුරාධපුර රාජධානිය සමයේ වාරිමාර්ග පද්ධතිය විශාල ලෙස දියුණු විය.",
    "පොළොන්නරුව රාජධානිය සමයේ පරාක්‍රමබාහු රජු විශාල වැව් ඉදි කළේය.",
    "වාරිමාර්ග පද්ධතිය නිසා කෘෂිකර්මය රට පුරා ව්‍යාප්ත විය.",
    "කෘෂිකර්මය දියුණු වීමත් සමඟ ගම්මාන ද විශාල ලෙස ව්‍යාප්ත විය.",
    "වෙළඳාම නිසා මහාතිත්ථ වරාය විදේශීය නැව්වලින් පිරී පැවතිණි.",
    "විදේශීය වෙළඳාම පොළොන්නරුව රාජධානිය කාලයේ ද අඛණ්ඩව පැවතිණි.",
    "අනුරාධපුර නගරය බෞද්ධ සංස්කෘතියේ කේන්ද්‍රස්ථානය ලෙස සැලකේ.",
    "පරාක්‍රමබාහු රජු පොළොන්නරුව නගරය අලංකාර ගොඩනැගිලිවලින් සැරසීය.",
    "බෞද්ධ සංස්කෘතියේ බලපෑම ගම්මාන ජීවිතයේ සෑම අංශයකටම දැනුණි.",
    "මහාතිත්ථ වරාය හරහා පැමිණි විදේශීය වෙළඳුන් මුතු මිලදී ගත්හ.",
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


def _answers_and_options(made):
    return [(c.options[c.answer], set(c.options)) for c in made]


def test_cloze_blanks_a_term_the_book_returns_to() -> None:
    sentences, index, _ = _book()
    counts = Counter(token for s in sentences for token in tokenize(s.text))

    made = cloze_questions(sentences, index, seed="v1")

    assert made
    for answer, options in _answers_and_options(made):
        # The blank, and every option offered beside it, recur in the book:
        # a word used once is as likely to be an extraction fault as a term.
        assert all(counts[option] >= MIN_OCCURRENCES for option in options), options
        assert counts[answer] >= MIN_OCCURRENCES


def test_cloze_never_offers_a_word_the_book_uses_once() -> None:
    sentences, index, _ = _book()
    # An extraction fault: a one-off, well-formed but meaningless word that
    # is rare, and so was exactly what the old generator reached for.
    junk = "විට්න්ගෙන්"
    sentences = [*sentences, Sentence(passage=1, segment_id="junk", text=f"{BOOK[0]} {junk}")]

    for _answer, options in _answers_and_options(cloze_questions(sentences, index, seed="v1")):
        assert junk not in options


def test_cloze_skips_a_sentence_that_leans_on_the_one_before() -> None:
    _, index, _ = _book()
    leaning = [
        Sentence(passage=i + 1, segment_id=f"s{i}", text=f"මේ ගැන {text}")
        for i, text in enumerate(BOOK)
    ]

    assert cloze_questions(leaning, index, seed="v1") == []


def test_cloze_asks_first_about_the_sentences_a_student_chose() -> None:
    sentences, index, _ = _book()
    wanted = [4, 9]  # the two sentences about the harbour

    made = cloze_questions(sentences, index, seed="v1", limit=2, first=wanted)

    assert {c.segment_id for c in made} == {"s4", "s9"}


def test_cloze_counts_recurrence_across_the_whole_book() -> None:
    sentences, index, _ = _book()
    book_wide = Counter(token for s in sentences for token in tokenize(s.text))
    part = sentences[:3]  # a chapter: alone, few of its words recur within it

    within_part = cloze_questions(part, index, seed="v1")
    across_book = cloze_questions(part, index, seed="v1", occurrences=book_wide)

    assert len(across_book) > len(within_part)
