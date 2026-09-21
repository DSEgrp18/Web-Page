"""The names the Modal deployment borrows from this package.

``deploy/modal_app.py`` cannot be imported here: it needs the ``modal`` client,
which is not a dependency of this package and is not installed in CI. So CI
lints that file and never executes it, and ruff does not resolve imports across
modules. That gap let ``verify`` ship referring to a ``REGRESSION_SENTENCES``
that has never existed, which would have failed on the first ``modal run`` —
after the weights had been uploaded, and in front of whoever was waiting for
the first GPU numbers this project has.

Reading the file rather than importing it keeps that check free: the names it
takes from ``sinhala_tts`` must be names ``sinhala_tts`` actually exports.

This does not check how they are used, only that they exist. It is a cheap
guard on a file no test can run, not a substitute for running it.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

MODAL_APP = Path(__file__).resolve().parents[1] / "deploy" / "modal_app.py"


def _imported_names() -> list[tuple[str, str]]:
    """Every ``from sinhala_tts.x import y`` in the deployment, as (module, name).

    Includes the imports inside functions, which is where most of them are: the
    container installs this package into its image, so the deployment defers
    those imports to where they run rather than paying them locally.
    """
    tree = ast.parse(MODAL_APP.read_text(encoding="utf-8"), filename=str(MODAL_APP))
    return [
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module
        and node.module.startswith("sinhala_tts")
        for alias in node.names
    ]


def test_the_deployment_imports_something_from_this_package() -> None:
    """A rename that emptied this list would make every other check vacuous."""
    assert _imported_names()


@pytest.mark.parametrize(("module", "name"), _imported_names())
def test_imported_name_exists(module: str, name: str) -> None:
    assert hasattr(importlib.import_module(module), name), (
        f"deploy/modal_app.py imports {name} from {module}, which does not export it. "
        f"`modal run` would fail on this."
    )


def test_case_attributes_the_verify_report_prints() -> None:
    """``verify`` formats each case; a renamed field fails only on Modal."""
    from sinhala_tts.regression_sentences import CASES

    source = MODAL_APP.read_text(encoding="utf-8")
    for attribute in ("case_id", "text"):
        assert f"case.{attribute}" in source, (
            f"verify no longer reads case.{attribute}; if the field was renamed, "
            f"this test is what should have caught it."
        )
        assert hasattr(CASES[0], attribute)
