"""Dense and hybrid retrieval baselines."""

from __future__ import annotations

from sinhala_documents.dense_retrieval import DenseIndex, HybridIndex
from sinhala_documents.passages import Passage
from sinhala_documents.retrieval import LexicalIndex
from sinhala_documents.structure import BlockRole


def _passage(text: str, *, page: int = 0, section: str = "") -> Passage:
    return Passage(
        passage_id=f"p{page}",
        document_version="v1",
        text=text,
        page_index=page,
        page_label=str(page + 1),
        section_path=(section,) if section else (),
        segment_ids=(f"s{page}",),
        roles=(BlockRole.PARAGRAPH,),
    )


COAL = _passage(
    "ගල් අඟුරු කර්මාන්තයේ ඇති වූ දියුණුව නිසා අතුරු ප්‍රතිලාභ රැසක් හිමි විය.",
    page=16,
    section="ගල් අඟුරු කර්මාන්තය",
)


def test_dense_finds_inflected_form_lexical_misses() -> None:
    """Documented lexical gap; dense n-grams partially bridge it."""
    assert LexicalIndex([COAL]).search("කර්මාන්තය") == ()
    hits = DenseIndex([COAL]).search("කර්මාන්තය")
    assert hits and hits[0].passage is COAL


def test_hybrid_returns_hits_when_either_arm_would() -> None:
    passages = (_passage("1814 වර්ෂයේ දී ජෝර්ජ් ස්ටීවන්සන් දුම්රිය."),)
    hits = HybridIndex(passages).search("දුම්රිය")
    assert hits
