"""The Celery entry point: ``celery -A sinhala_reader.celery_worker worker``.

A module rather than a factory reference, because ``-A module:factory`` does not
work: Celery's ``find_app`` returns whatever the name resolves to and does not
call it, so ``-A sinhala_reader.queue:build_app`` hands Celery a function and
fails. Tested rather than assumed, after a comment asserting the opposite.

It exists as a separate module rather than as an ``app`` in :mod:`.queue` so
that Celery stays an extra. Importing :mod:`.queue` must not import Celery — a
contributor working on the reader interface should not need a broker library to
run the API's tests — and importing *this* module obviously does, which is fine
because the only thing that imports it is a worker.
"""

from __future__ import annotations

from .queue import build_app

#: The application a worker serves. Built at import, which is when a worker
#: starts and never during a request.
app = build_app()
