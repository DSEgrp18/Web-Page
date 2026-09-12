"""The answerer: evidence or abstention, never a plausible invention."""

from __future__ import annotations

from sinhala_documents.answerer import answer_question
from sinhala_documents.passages import Passage
from sinhala_documents.structure import BlockRole


def passage(text: str, *, page: int = 0, section: str = "") -> Passage:
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


STEAM = passage(
    "1814 වර්ෂයේ දී ජෝර්ජ් ස්ටීවන්සන් වාෂ්ප බලයෙන් ක්‍රියා කරන දුම්රිය එන්ජිම නිපදවීය.",
    page=17,
    section="ප්‍රවාහනයේ දියුණුව",
)
COAL = passage("ගල් අඟුරු කර්මාන්තයේ දියුණුව නිසා අතුරු ප්‍රතිලාභ රැසක් හිමි විය.", page=16)


def test_an_answer_is_the_book_s_own_supported_words() -> None:
    answer = answer_question("දුම්රිය එන්ජිම නිපදවූයේ කවුද", [COAL, STEAM])

    assert answer.abstained is False
    assert answer.answer == STEAM.text
    assert answer.citations[0].quote == STEAM.text
    assert answer.citations[0].section == "ප්‍රවාහනයේ දියුණුව"
    assert answer.citations[0].segment_ids == ("s17",)


def test_no_matching_evidence_means_an_explicit_abstention() -> None:
    answer = answer_question("පරිගණක ජාල ආරක්ෂාව ගැන කියන්න", [COAL, STEAM])

    assert answer.abstained is True
    assert answer.answer is None
    assert answer.citations == ()


def test_a_hit_on_question_scaffolding_alone_is_not_an_answer() -> None:
    answer = answer_question("කියන්න", [passage("මෙය කියන්න යනුවෙන් සඳහන් වේ.")])

    assert answer.abstained is True


def test_an_empty_question_is_not_answered() -> None:
    assert answer_question("   ", [STEAM]).abstained is True
