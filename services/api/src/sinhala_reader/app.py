"""The reader API: upload a book, get its segments, hear them, resume where you were.

This is the spine CLAUDE.md's step 3 asks for — digital PDF to selected page to
audio to pause and resume — with the parts that do not exist yet named rather
than faked.

Three rules run through every route:

* **Ownership is the store's job, not the route's.** Every read takes an owner
  and returns nothing for anyone else's document, so a forgotten check is a
  missing argument rather than a silent leak.
* **A missing document and someone else's document look identical.** Both are
  404. A 403 on an id that exists confirms it exists, and these are private
  books belonging to identifiable students.
* **Placeholder audio announces itself.** Every audio response carries whether a
  real model produced it, in a header and in the manifest, because a listener
  cannot tell a tone from speech they were not expecting.

What is deliberately absent: object storage. Accounts, a database and a job
queue are not — ``SINHALA_READER_AUTH=sessions`` gives real sign-in,
``SINHALA_READER_DATABASE_URL`` selects PostgreSQL, and
``SINHALA_READER_QUEUE=celery`` moves preparation onto a broker. Without each,
the placeholder is used and ``/readiness`` says so on every call.

See ``security.py``, ``storage.py`` and ``preparation.py`` — each says what
stands in for the real thing and what that costs.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sinhala_documents.answering import (
    AnswerAdapter,
    ExtractiveAnswerer,
)
from sinhala_tts.adapter import TtsAdapter

from .accounts import router as accounts_router
from .adapters import build_adapter, warm
from .answers import build_answerer
from .audio import SynthesisService
from .preparation import (
    PreparationService,
    in_thread,
    inline,
    reap_periodically,
)
from .queue import build_app, send_prepare, uses_celery
from .ratelimit import RateLimiter, build_rate_limiter
from .routes import classes, documents, operations, publishing, reading, study
from .routes.common import REAL_MODEL_HEADER
from .security import (
    OWNER_HEADER,
    allowed_origins,
    check_configuration,
)
from .storage import (
    Store,
    build_store,
)

__all__ = ["REAL_MODEL_HEADER", "Deps", "app", "create_app"]


class Deps:
    """The composition root.

    Implementations are chosen once, here, rather than imported where they are
    used — so a test swaps a store or an adapter without patching a module, and
    a deployment swaps them without touching a route.
    """

    def __init__(
        self,
        store: Store | None = None,
        adapter: TtsAdapter | None = None,
        *,
        answerer: AnswerAdapter | None = None,
        run_in_background: bool = True,
        warm_on_start: bool = True,
        reap_stalled: bool | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.store = store or build_store()
        #: Chosen from configuration, defaulting to counting in this process.
        self.rate_limiter = rate_limiter or build_rate_limiter()
        # Chosen from configuration, defaulting to the labelled placeholder.
        self.adapter = adapter or build_adapter()
        #: Chosen from configuration, defaulting to the book's own words.
        self.answerer = answerer or build_answerer()
        #: What runs when the configured answerer cannot. Always extractive:
        #: it needs no provider, so it cannot fail the same way.
        self.fallback_answerer = ExtractiveAnswerer()
        #: Load the checkpoint at start-up rather than in the first request.
        #: Tests turn it off to hold an adapter in a chosen state.
        self.warm_on_start = warm_on_start
        #: Look for stalled jobs, now and every minute. Follows where work runs:
        #: a job run inline cannot outlive the request that ran it, so a test
        #: running work inline has nothing to reap and no thread to leave behind.
        self.reap_stalled = run_in_background if reap_stalled is None else reap_stalled
        #: Where preparation runs. ``run_in_background=False`` wins over
        #: configuration: a test asking for inline work must get inline work,
        #: not whatever a stray environment variable selects.
        self.celery = build_app() if run_in_background and uses_celery() else None
        self.preparation = PreparationService(
            self.store, dispatch=self._dispatcher(run_in_background)
        )
        self.synthesis = SynthesisService(self.adapter, self.store)

    def _dispatcher(self, run_in_background: bool):
        if not run_in_background:
            return inline
        if self.celery is not None:
            celery = self.celery

            def to_the_queue(service, document_id: str, job_id: str) -> None:
                send_prepare(celery, document_id, job_id)

            return to_the_queue
        return in_thread


def create_app(deps: Deps | None = None) -> FastAPI:
    """Build the app around an explicit set of dependencies."""
    # Before anything is built: sessions without a CSRF key must not start.
    check_configuration()
    deps = deps or Deps()
    app = FastAPI(
        title="Sinhala Accessible Reader",
        version="0.0.1",
        summary="Upload Sinhala PDFs, Word documents and images, then read and listen.",
    )
    app.state.deps = deps

    # Load the checkpoint while the process starts rather than inside the first
    # request. It takes over a minute on this hardware; a reader who presses
    # play and waits that long has been failed whatever happens next.
    app.state.warm_up = warm(deps.adapter) if deps.warm_on_start else None
    app.state.reaper = reap_periodically(deps.store) if deps.reap_stalled else None

    # Register, sign in, sign out, change a password. Mounted whatever the auth
    # mode is: in development the routes answer 503 and say which setting turns
    # them on, which is more use than a 404 that looks like a missing feature.
    app.include_router(accounts_router)

    # The reader UI is served from its own origin, so without this the browser
    # blocks every request before it leaves the machine and the interface can
    # only say it is offline. Unset means no browser may call this API: the
    # origins have to be named, and `X-Reader-Real-Model` has to be exposed
    # explicitly or the reader cannot tell a placeholder tone from speech.
    origins = allowed_origins()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            # `Range` has to be allowed or the preflight for a partial PDF read
            # fails, and pdf.js falls back to fetching whole books.
            allow_headers=[OWNER_HEADER, "Authorization", "Content-Type", "Range"],
            # Cross-origin, a header the browser will not expose does not exist
            # as far as the page is concerned: without `Content-Range` pdf.js
            # cannot tell which bytes it got, and without `X-Reader-Real-Model`
            # the reader cannot tell a placeholder tone from speech.
            expose_headers=[REAL_MODEL_HEADER, "Content-Range", "Accept-Ranges", "Content-Length"],
            # Identity travels in a header, not a cookie. Allowing credentials
            # would let a third-party page ride along on an ambient session the
            # moment real authentication replaces the header.
            allow_credentials=False,
            max_age=600,
        )

    # The routes, one module per area; see routes/__init__.py.
    operations.register(app, deps)
    documents.register(app, deps)
    reading.register(app, deps)
    study.register(app, deps)
    classes.register(app, deps)
    publishing.register(app, deps)

    return app


#: The app a server runs. Tests build their own with explicit dependencies.
app = create_app()
