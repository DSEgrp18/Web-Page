"""The entry point a server runs: ``uvicorn sinhala_reader.serve:app``.

It exists so that reading :file:`.env` happens in exactly one place — before
anything reads :data:`os.environ` — and **not** on importing
:mod:`sinhala_reader.app`.

That distinction is the whole point of the module. Configuration is read at the
composition root while the app is being built, so a ``.env`` loaded at import
time would reach every importer, the test suite included. A developer whose
``.env`` names a database would silently change what the tests exercise, and
tests that quietly talk to a real database are how a suite starts passing for
reasons nobody chose. This project has already been bitten once by ambient
configuration leaking into a test run.

So: importing :mod:`.app` configures nothing, and running a server is an
explicit act that loads the file first.
"""

from __future__ import annotations

from .envfile import load_env_file

#: Names set from the file, for the startup log. The names only — a value here
#: may be a credential, and this is the one place tempted to print it.
loaded_from_file = load_env_file()

from .app import create_app  # noqa: E402  (must follow the load above)

app = create_app()
