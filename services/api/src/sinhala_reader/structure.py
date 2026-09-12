"""Which structure adapter this process uses, chosen once from configuration.

The same shape as :mod:`.adapters`, and for the same reason: what a deployment
gets should be a setting, not an edit to a source file.

The default is off, and unlike the voice that is not merely a safe default but
the one CLAUDE.md requires to stay shippable. Structure inference sends a page
of a reader's document to an external provider, so it has to be chosen
deliberately, and everything downstream has to work without it.

An unrecognised value stops the process rather than quietly falling back, which
is how the voice behaves and for the same reason: a typo in a deployment
variable must not silently change what readers get.
"""

from __future__ import annotations

import logging
import os

from sinhala_documents.gemini import GeminiStructure
from sinhala_documents.structuring import DeterministicStructure, StructureAdapter

log = logging.getLogger(__name__)

#: Which structure adapter to use. See :data:`MODES`.
STRUCTURE_ENV = "SINHALA_READER_STRUCTURE"

DETERMINISTIC = "deterministic"
GEMINI = "gemini"
MODES = (DETERMINISTIC, GEMINI)


def structure_mode() -> str:
    """The configured mode, defaulting to no provider at all."""
    return os.environ.get(STRUCTURE_ENV, "").strip().lower() or DETERMINISTIC


def build_structure() -> StructureAdapter:
    """Build the structure adapter this process will use.

    Raises:
        ValueError: if the mode is not one of :data:`MODES`. Deliberately fatal.
    """
    mode = structure_mode()
    if mode == DETERMINISTIC:
        return DeterministicStructure()
    if mode == GEMINI:
        return GeminiStructure()
    raise ValueError(
        f"{STRUCTURE_ENV}={mode!r} is not a structure source this server knows. "
        f"Use one of: {', '.join(MODES)}."
    )


def structure_limitations() -> list[str]:
    """What a deployment should know about the structure setting, for readiness.

    The deterministic entry is not a warning that something is broken. It says
    what a reader will and will not get, in the same register as the others: a
    caption read in the middle of a sentence is a real effect on a real person,
    and a deployment that has not chosen deserves to see it named.
    """
    mode = structure_mode()
    if mode == GEMINI:
        return [
            "Page structure is inferred by an external provider, which means each "
            "page of an uploaded document is sent to Google. Every response is "
            "checked character for character against the extracted text and a page "
            "that differs is discarded.",
        ]
    return [
        "Page structure is not being inferred, so headings and captions are not "
        "identified. A caption is read in sequence with the paragraph beside it, "
        "and a section number is read as a decimal. Set "
        f"{STRUCTURE_ENV}=gemini to identify them.",
    ]
