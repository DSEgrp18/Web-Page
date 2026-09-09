"""The fixed regression set.

Cheap guards on a file whose value comes entirely from being stable and
meaningful. A duplicate id would silently overwrite one case's audio with
another's; a case that normalises to nothing would be skipped every run and
quietly stop testing anything.
"""

from __future__ import annotations

import pytest

from sinhala_tts.normalize import contains_sinhala, is_speakable, to_model_input
from sinhala_tts.regression_sentences import CASES, case_by_id


def test_case_ids_are_unique() -> None:
    """Ids name the output files; a duplicate would overwrite a case's audio."""
    ids = [case.case_id for case in CASES]
    assert len(ids) == len(set(ids))


def test_every_case_explains_itself() -> None:
    """A case nobody can explain is a case nobody can judge the failure of."""
    for case in CASES:
        assert case.why.strip(), case.case_id
        assert case.text.strip(), case.case_id


def test_every_case_is_sinhala() -> None:
    for case in CASES:
        assert contains_sinhala(case.text), case.case_id


def test_every_case_survives_normalisation_to_speakable_ascii() -> None:
    """A case that normalises to nothing would be skipped on every run.

    It would keep passing, in the sense of never failing, while testing nothing.
    """
    for case in CASES:
        model_text = to_model_input(case.text)
        assert is_speakable(model_text), f"{case.case_id} normalises to {model_text!r}"
        assert model_text.isascii(), case.case_id


def test_the_number_cases_actually_carry_numbers() -> None:
    """These two exist to prove digits survive; if the digits were edited out of
    the text, they would pass while testing the opposite of their purpose."""
    for case_id in ("page-reference", "year"):
        case = case_by_id(case_id)
        assert any(character.isdigit() for character in case.text), case_id


def test_case_by_id_rejects_unknown_ids() -> None:
    with pytest.raises(KeyError):
        case_by_id("no-such-case")
