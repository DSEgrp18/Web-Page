"""Choosing a structure, and surviving the chooser being wrong.

A book must stay readable when a provider is down, out of quota, or returning
somebody else's text, and a reader who wanted chapter four does not care which.
"""

from __future__ import annotations

import logging

from sinhala_documents.blocks import Block
from sinhala_documents.model import QualityState
from sinhala_documents.structure import BlockRole
from sinhala_documents.structuring import (
    DeterministicStructure,
    StructureAdapter,
    StructureUnavailable,
    structure_page,
)

PAGE = "1.1 ආරම්භය\nකාර්මික විප්ලවය ඇරඹිණි."


class Fake(StructureAdapter):
    def __init__(self, result=None, raises: Exception | None = None) -> None:
        self._result = result
        self._raises = raises

    @property
    def version(self) -> str:
        return "fake-1"

    def blocks_for(self, page_text: str):
        if self._raises is not None:
            raise self._raises
        return self._result


def _faithful() -> tuple[Block, ...]:
    return (
        Block(BlockRole.HEADING, "1.1 ආරම්භය", level=2),
        Block(BlockRole.PARAGRAPH, "කාර්මික විප්ලවය ඇරඹිණි."),
    )


def test_a_verified_structuring_is_used_and_carries_its_provenance() -> None:
    page = structure_page(PAGE, Fake(_faithful()))
    assert page.blocks == _faithful()
    assert page.version == "fake-1"
    assert page.quality is QualityState.ACCEPTED
    assert page.note == ""


def test_an_unavailable_provider_is_the_normal_path_not_a_defect() -> None:
    """No provider configured is the documented default. Nothing is wrong here."""
    page = structure_page(PAGE, Fake(raises=StructureUnavailable("no quota")))
    assert page.quality is QualityState.ACCEPTED
    assert page.version == DeterministicStructure().version
    assert [b.role for b in page.blocks] == [BlockRole.UNKNOWN]
    assert "unavailable" in page.note


def test_an_unverifiable_answer_falls_back_and_is_flagged() -> None:
    """The signal that a model is misbehaving, which must not be lost."""
    invented = (Block(BlockRole.PARAGRAPH, "මෙය පොතේ නැති වාක්‍යයකි."),)
    page = structure_page(PAGE, Fake(invented))
    assert page.quality is QualityState.NEEDS_REVIEW
    assert page.version == DeterministicStructure().version
    assert [b.role for b in page.blocks] == [BlockRole.UNKNOWN]


def test_unavailable_and_wrong_are_not_the_same_outcome() -> None:
    """Collapsing them hides misbehaviour behind ordinary network noise."""
    down = structure_page(PAGE, Fake(raises=StructureUnavailable("timeout")))
    wrong = structure_page(PAGE, Fake((Block(BlockRole.PARAGRAPH, "වෙනත් පොතක්"),)))
    assert down.quality is not wrong.quality


def test_an_adapter_bug_does_not_take_the_book_down(caplog) -> None:
    page = structure_page(PAGE, Fake(raises=TypeError("bad adapter")))
    assert page.quality is QualityState.NEEDS_REVIEW
    assert page.blocks
    assert "failed" in page.note


def test_the_page_is_still_readable_in_every_failure(caplog) -> None:
    """The property that matters: text survives whatever the provider does."""
    caplog.set_level(logging.DEBUG)
    for adapter in (
        Fake(raises=StructureUnavailable("down")),
        Fake(raises=RuntimeError("bug")),
        Fake((Block(BlockRole.PARAGRAPH, "not this book"),)),
        Fake(()),
    ):
        page = structure_page(PAGE, adapter)
        assert "".join(b.text for b in page.blocks).strip() == PAGE.strip()


def test_a_note_never_contains_document_text() -> None:
    """CLAUDE.md forbids logging private passages; a note is shown and logged."""
    secret = "රහසිගත වාක්‍යයකි"
    page = structure_page(secret, Fake((Block(BlockRole.PARAGRAPH, "වෙනස් දෙයක්"),)))
    assert secret not in page.note


def test_the_deterministic_adapter_is_used_directly_without_a_round_trip() -> None:
    page = structure_page(PAGE, DeterministicStructure())
    assert page.quality is QualityState.ACCEPTED
    assert page.version == "deterministic-1"


def test_an_empty_page_produces_no_blocks() -> None:
    assert structure_page("   ", DeterministicStructure()).blocks == ()


def test_unknown_is_not_paragraph() -> None:
    """A page nobody classified stays distinguishable from one classified as prose."""
    blocks = DeterministicStructure().blocks_for(PAGE)
    assert blocks[0].role is BlockRole.UNKNOWN
