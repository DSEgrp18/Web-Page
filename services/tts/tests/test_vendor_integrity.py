"""The vendored front end must stay exactly as the model was trained with.

If this test fails, someone edited `sinhala_text.py` — reformatted it, "fixed" a
lint warning, or re-copied a different version. Any of those silently changes
how the model pronounces text, and the change would otherwise be invisible in
review because the file looks like ordinary Python.

Restore the file rather than updating the hash, unless the model itself was
retrained with a new front end. In that case update the hash, the manifest, and
PROVENANCE.md in the same commit.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parents[1] / "src" / "sinhala_tts" / "vendor"
FRONT_END = VENDOR_DIR / "sinhala_text.py"

# SHA-256 of the file with line endings normalised to LF. Line endings are the
# one thing this repository is allowed to change about the file (.gitattributes
# stores text as LF), so hashing the normalised bytes gives a value that is
# identical on Windows, Linux, and macOS checkouts.
EXPECTED_SHA256_LF = "c36d9864696b87ea46743cd6c860aeb14a44d9c6e9d979062f97554b9ecdd0dd"

# The file as delivered in the model bundle, which uses CRLF. Recorded for
# provenance; not asserted, because the repository legitimately normalises it.
DELIVERED_SHA256_CRLF = "f8f41fa44de13bb93a6f1de47a6b1d1aabc3162feadd6171c170ea8520919c92"


def _normalised_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_front_end_is_present() -> None:
    assert FRONT_END.is_file(), (
        f"{FRONT_END} is missing. The Sinhala front end is required for inference; "
        "without it every Sinhala word tokenises to [UNK] and the model emits babble."
    )


def test_front_end_is_unmodified() -> None:
    actual = _normalised_sha256(FRONT_END)
    assert actual == EXPECTED_SHA256_LF, (
        "The vendored Sinhala front end has changed.\n"
        f"  expected {EXPECTED_SHA256_LF}\n"
        f"  actual   {actual}\n"
        "This file defines the text the model was trained on. Restore it instead of "
        "updating this hash, unless the model was retrained with a new front end."
    )


def test_provenance_is_recorded() -> None:
    """The hashes in the test and in PROVENANCE.md must not drift apart."""
    provenance = (VENDOR_DIR / "PROVENANCE.md").read_text(encoding="utf-8")
    assert EXPECTED_SHA256_LF in provenance
    assert DELIVERED_SHA256_CRLF in provenance
