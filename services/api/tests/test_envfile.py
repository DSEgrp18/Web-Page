"""The .env loader, whose whole job is to be unsurprising.

The rules it must not break are the ones that would otherwise cause a quiet
misconfiguration rather than a visible failure.
"""

from __future__ import annotations

from pathlib import Path

from sinhala_reader.envfile import ENV_FILENAME, find_env_file, load_env_file, parse_env


def test_reads_plain_assignments() -> None:
    assert parse_env("A=1\nB=two\n") == {"A": "1", "B": "two"}


def test_ignores_blank_lines_and_comments() -> None:
    assert parse_env("\n# a comment\n\nA=1\n  # indented\n") == {"A": "1"}


def test_accepts_a_leading_export() -> None:
    """People paste the line they were using in their shell."""
    assert parse_env("export GEMINI_API_KEY=abc") == {"GEMINI_API_KEY": "abc"}


def test_strips_matched_quotes_only() -> None:
    assert parse_env("A='x y'\nB=\"z\"\nC='unbalanced\n") == {
        "A": "x y",
        "B": "z",
        "C": "'unbalanced",
    }


def test_keeps_characters_a_key_may_legitimately_contain() -> None:
    """A credential is not a word. = and # inside a value are not delimiters."""
    assert parse_env("K=ab=cd#ef") == {"K": "ab=cd#ef"}


def test_a_line_without_an_equals_is_skipped_not_fatal() -> None:
    """A typo in a developer convenience file must not stop a server booting."""
    assert parse_env("nonsense\nA=1") == {"A": "1"}


def test_the_real_environment_always_wins(tmp_path: Path) -> None:
    """The rule that matters most.

    A stale .env must never override what a deployment set, and an auth mode
    left in a file must never be able to weaken a server that was configured
    properly.
    """
    path = tmp_path / ENV_FILENAME
    path.write_text("SET_BY_FILE=file\nALREADY_SET=file\n", encoding="utf-8")
    environ = {"ALREADY_SET": "environment"}

    applied = load_env_file(path, environ=environ)

    assert environ["ALREADY_SET"] == "environment"
    assert environ["SET_BY_FILE"] == "file"
    assert applied == ["SET_BY_FILE"]


def test_returns_names_only_so_a_caller_cannot_log_a_secret(tmp_path: Path) -> None:
    path = tmp_path / ENV_FILENAME
    path.write_text("GEMINI_API_KEY=super-secret\n", encoding="utf-8")
    environ: dict[str, str] = {}

    applied = load_env_file(path, environ=environ)

    assert applied == ["GEMINI_API_KEY"]
    assert "super-secret" not in str(applied)


def test_a_byte_order_mark_does_not_become_part_of_the_first_key(tmp_path: Path) -> None:
    """Notepad and PowerShell write one, and this project is developed on Windows.

    Read as plain utf-8 the mark joins the first name, so a key on line one is
    present in the file and invisible to the service.
    """
    path = tmp_path / ENV_FILENAME
    path.write_text("GEMINI_API_KEY=abc\n", encoding="utf-8-sig")
    environ: dict[str, str] = {}

    assert load_env_file(path, environ=environ) == ["GEMINI_API_KEY"]
    assert environ["GEMINI_API_KEY"] == "abc"


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert load_env_file(tmp_path / "nothing-here", environ={}) == []


def test_an_unreadable_file_is_treated_as_absent(tmp_path: Path) -> None:
    """A directory named .env, for instance. Never the thing that stops a boot."""
    path = tmp_path / ENV_FILENAME
    path.mkdir()
    assert load_env_file(path, environ={}) == []


def test_nothing_is_interpolated(tmp_path: Path) -> None:
    """A format that can reference other values can be made to leak them."""
    path = tmp_path / ENV_FILENAME
    path.write_text("A=$OTHER\nB=${OTHER}\n", encoding="utf-8")
    environ: dict[str, str] = {"OTHER": "leaked"}

    load_env_file(path, environ=environ)

    assert environ["A"] == "$OTHER"
    assert environ["B"] == "${OTHER}"


def test_finds_the_file_from_a_subdirectory(tmp_path: Path) -> None:
    """The service is run from the repository root and from services/api."""
    (tmp_path / ENV_FILENAME).write_text("A=1\n", encoding="utf-8")
    deep = tmp_path / "services" / "api"
    deep.mkdir(parents=True)

    assert find_env_file(deep) == tmp_path / ENV_FILENAME


def test_finds_nothing_when_there_is_nothing(tmp_path: Path) -> None:
    assert find_env_file(tmp_path) is None
