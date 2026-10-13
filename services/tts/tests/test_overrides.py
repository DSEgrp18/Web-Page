"""Pronunciation overrides: whole words, opt-in, and invisible when off."""

from __future__ import annotations

import pytest

from sinhala_tts import overrides
from sinhala_tts.adapter import DevelopmentAdapter
from sinhala_tts.normalize import NORMALIZER_VERSION, to_model_input
from sinhala_tts.overrides import ENV, OverrideFileError, parse

GANGA = parse("ගඟ\tgangga\n")

#: Words that sound right today. No override may change how they are spelled.
UNCHANGED = [
    "ශ්‍රී ලංකාව ඉන්දියන් සාගරයේ පිහිටි දිවයිනකි.",
    "අනුරාධපුරය වසර දහසකට වැඩි කාලයක් අගනුවර විය.",
    "ගංගා නදිය, සිංහල භාෂාව සහ අම්බලම.",
    "පිටුව 42 බලන්න.",
]


def test_a_listed_word_is_spelled_as_listed() -> None:
    assert to_model_input("ගඟ") == "ganga"
    assert GANGA.model_input("ගඟ") == "gangga"


def test_only_whole_words_match() -> None:
    """ගඟුල contains ගඟ but is a different word, and keeps today's spelling."""
    assert GANGA.model_input("ගඟුල") == to_model_input("ගඟුල") == "gangula"
    assert GANGA.model_input("අඟල") == "angala"


def test_punctuation_spacing_and_other_words_are_kept() -> None:
    sentence = "මහ ගඟ, ගලා යයි!"
    assert GANGA.model_input(sentence) == "maha gangga, galaa yayi!"
    assert to_model_input(sentence) == "maha ganga, galaa yayi!"


def test_text_is_matched_after_nfc_normalisation() -> None:
    entry = parse("කෝපි\tkoopi\n")
    decomposed = "ක" + "ෙ" + "්" + "ප" + "ි"  # not a word; NFC must not invent a match
    assert entry.model_input(decomposed) == to_model_input(decomposed)
    composed = "කෝපි"
    assert entry.model_input(composed) == "koopi"


@pytest.mark.parametrize("sentence", UNCHANGED)
def test_sentences_without_a_listed_word_are_unchanged(sentence: str) -> None:
    from sinhala_tts.normalize import to_speech_text

    spoken = to_speech_text(sentence)
    assert GANGA.model_input(spoken) == to_model_input(sentence)


@pytest.mark.parametrize(
    "line",
    [
        "ගඟ",  # no spelling
        "ගඟ\tGangga",  # not lowercase
        "ගඟ\tgang ga",  # two words
        "ගඟ\tgaṅga",  # not ASCII
        "මහ ගඟ\tmahagangga",  # not one word
        "ganga\tgangga",  # not Sinhala
    ],
)
def test_malformed_entries_are_refused(line: str) -> None:
    with pytest.raises(OverrideFileError):
        parse(line + "\n")


def test_a_word_listed_twice_differently_is_refused() -> None:
    with pytest.raises(OverrideFileError, match="twice"):
        parse("ගඟ\tgangga\nගඟ\tgaga\n")


def test_the_version_follows_the_entries() -> None:
    assert parse("# a comment\nගඟ\tgangga\n").version == GANGA.version
    assert parse("ගඟ\tgaga\n").version != GANGA.version


def test_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV, raising=False)
    assert overrides.active() is None
    assert overrides.normalizer_version() == NORMALIZER_VERSION
    assert DevelopmentAdapter().prepare_text("ගඟ") == ("ගඟ", "ganga")


def test_switched_on_it_reaches_synthesis_and_the_cache_key(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = DevelopmentAdapter()
    monkeypatch.delenv(ENV, raising=False)
    original_key = adapter.cache_key("ගඟ", "si-female")
    other_key = adapter.cache_key("ගංගා", "si-female")

    table = tmp_path / "overrides.tsv"
    table.write_text("ගඟ\tgangga\tlisteners preferred it\n", encoding="utf-8")
    monkeypatch.setenv(ENV, str(table))

    assert adapter.prepare_text("ගඟ") == ("ගඟ", "gangga")
    # Stored text from the pipeline is re-spelled too: it is applied at synthesis.
    assert adapter.prepare_text("ignored", prepared=("ගඟ", "ganga"))[1] == "gangga"
    assert adapter.cache_key("ගඟ", "si-female") != original_key
    # Every clip records that overrides were on, so even an unaffected word's
    # audio is its own variant.
    assert adapter.cache_key("ගංගා", "si-female") != other_key
    assert adapter.synthesize("ගඟ", "si-female").metadata.normalizer_version.startswith(
        f"{NORMALIZER_VERSION}+ovr-"
    )


def test_a_named_file_that_is_missing_is_an_error_not_silence(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV, str(tmp_path / "absent.tsv"))
    with pytest.raises(OverrideFileError, match="cannot be read"):
        overrides.active()
