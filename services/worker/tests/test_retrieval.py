"""Lexical retrieval over one document's passages."""

from __future__ import annotations

from sinhala_documents.passages import Passage
from sinhala_documents.retrieval import LexicalIndex, tokenize
from sinhala_documents.structure import BlockRole


def _passage(text: str, *, page: int = 0, section: str = "", version: str = "v1") -> Passage:
    return Passage(
        passage_id=f"p{page}_{abs(hash(text)) % 9999}",
        document_version=version,
        text=text,
        page_index=page,
        page_label=str(page + 1),
        section_path=(section,) if section else (),
        segment_ids=(f"s{page}",),
        roles=(BlockRole.PARAGRAPH,),
    )


STEAM = _passage(
    "1814 වර්ෂයේ දී ජෝර්ජ් ස්ටීවන්සන් වාෂ්ප බලයෙන් ක්‍රියා කරන දුම්රිය එන්ජිම නිපදවී ය.",
    page=17,
    section="ප්‍රවාහනයේ දියුණුව",
)
COAL = _passage(
    "ගල් අඟුරු කර්මාන්තයේ ඇති වූ දියුණුව නිසා අතුරු ප්‍රතිලාභ රැසක් හිමි විය.",
    page=16,
    section="ගල් අඟුරු කර්මාන්තය",
)
POST = _passage(
    "1840 දී පෙනී තැපැල් සේවය නමින් නව තැපැල් සේවයක් එංගලන්තයේ ආරම්භ කෙරිණි.",
    page=18,
    section="සන්නිවේදනය",
)
ALL = (STEAM, COAL, POST)


def test_tokenising_keeps_the_joiner_inside_a_conjunct() -> None:
    """Splitting on the joiner turns one Sinhala word into two that match nothing."""
    assert tokenize("ක්‍රියා") == ["ක්‍රියා"]


def test_tokenising_keeps_digits() -> None:
    """A question about a year has to be able to find the year."""
    assert "1814" in tokenize("1814 වර්ෂයේ දී")


def test_the_relevant_passage_comes_first() -> None:
    hits = LexicalIndex(ALL).search("දුම්රිය එන්ජිම නිපදවූයේ කවුද")
    assert hits[0].passage is STEAM


def test_a_question_about_a_year_finds_that_year() -> None:
    hits = LexicalIndex(ALL).search("1840 දී සිදු වූයේ කුමක් ද")
    assert hits[0].passage is POST


def test_nothing_matching_returns_nothing() -> None:
    """Returning the best of a bad set hands the answerer evidence for a question
    the book does not address, which is how a confident wrong answer happens."""
    assert LexicalIndex(ALL).search("පරිගණක ජාල ආරක්ෂාව ගැන කුමක් කියැවේ ද") == ()


def test_a_match_on_nothing_but_common_words_is_not_a_match() -> None:
    """The real failure, found on the book and not in a fixture.

    Asked about computer network security over sixteen pages of a history
    textbook, BM25 returned three passages matching "කරන්න" (do) and "විස්තර"
    (description) and no content word at all. A three-passage fixture has
    nowhere to hide this; a real book does.
    """
    passages = [_passage(f"මෙය පොදු වචන ඇති {n} වන ඡේදයයි. කරන්න ද විස්තර.", page=n) for n in range(8)]
    passages.append(_passage("දුම්රිය එන්ජිම නිපදවී ය. කරන්න ද විස්තර.", page=9))
    index = LexicalIndex(passages)

    # "කරන්න" and "ද" are in every passage: they cannot distinguish anything.
    assert index.search("කරන්න ද") == ()
    # A content word still works, and still brings its common companions along.
    hits = index.search("දුම්රිය කරන්න ද")
    assert len(hits) == 1
    assert "දුම්රිය" in hits[0].terms


def test_an_empty_question_returns_nothing() -> None:
    assert LexicalIndex(ALL).search("   ") == ()


def test_an_empty_index_returns_nothing() -> None:
    assert LexicalIndex([]).search("ඕනෑම දෙයක්") == ()


def test_the_limit_is_respected() -> None:
    assert len(LexicalIndex(ALL).search("දී", limit=2)) <= 2


def test_a_hit_says_which_terms_matched() -> None:
    """A retrieval you cannot explain is one you can only replace, never fix."""
    hits = LexicalIndex(ALL).search("දුම්රිය එන්ජිම")
    assert "දුම්රිය" in hits[0].terms


def test_a_word_in_every_passage_never_scores_a_passage_down() -> None:
    """Negative idf would punish a passage for using a word the question used."""
    common = [_passage(f"දී පොදු වචනය {n}", page=n) for n in range(5)]
    for hit in LexicalIndex(common).search("දී"):
        assert hit.score >= 0


def test_the_index_holds_one_document_so_there_is_nothing_to_leak() -> None:
    """Authorization by construction: another reader's book is not in here."""
    index = LexicalIndex(ALL)
    assert index.document_version == "v1"
    for hit in index.search("දුම්රිය"):
        assert hit.passage in ALL


def test_an_empty_index_has_no_version_to_report() -> None:
    assert LexicalIndex([]).document_version is None


def test_inflection_is_not_matched_and_that_is_documented() -> None:
    """The honest limit, asserted so it cannot be forgotten or quietly assumed away.

    කර්මාන්තයේ and කර්මාන්තය are the same word in different cases. Lexical
    retrieval misses it, and this is the strongest argument for measuring a
    dense arm rather than declaring lexical sufficient.
    """
    hits = LexicalIndex([COAL]).search("කර්මාන්තය")
    assert hits == ()


def test_a_sinhala_word_is_one_token_not_a_pile_of_letters() -> None:
    r"""Python's \w excludes combining marks, and Sinhala vowel signs are marks.

    With \w, දුම්රිය tokenises as ද, ම, ර, ය — four fragments shared by half
    the book. Retrieval still returns results, ranked by nonsense, which is what
    makes the failure dangerous rather than merely wrong.
    """
    assert tokenize("දුම්රිය") == ["දුම්රිය"]
    assert tokenize("කර්මාන්තයේ ඇති වූ") == ["කර්මාන්තයේ", "ඇති", "වූ"]


def test_a_question_word_the_book_rarely_uses_still_gets_through() -> None:
    """The residual gap, asserted so nobody assumes it was fixed.

    Question words like "කරන්න" are rare in a history textbook, so document
    frequency calls them informative and the common-term floor lets them
    through. Only a stopword list would catch them, and there is no evaluated
    Sinhala one here. This is why abstention belongs to the answerer.
    """
    passages = [_passage(f"ඉතිහාස ඡේදය {n} මෙහි ඇත.", page=n) for n in range(8)]
    passages.append(_passage("මෙය කරන්න යනුවෙන් සඳහන් වේ.", page=9))
    hits = LexicalIndex(passages).search("පරිගණක ජාල ආරක්ෂාව කරන්න")
    assert hits, "documents the gap: this returns a hit, and should not be trusted"
    assert hits[0].terms == ("කරන්න",)
