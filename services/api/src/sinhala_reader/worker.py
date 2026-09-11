"""The worker process's entry point: ``celery -A sinhala_reader.worker worker``.

A separate module from :mod:`.queue` because importing it *builds* the Celery
application, and that reads configuration and fails if there is no broker. The
API imports ``queue`` on every start-up whatever dispatcher is selected, so
building an app there would make a broker mandatory for everyone.

This module is only ever imported by a worker, which by definition has one.

The worker needs the **same database as the API**. It has no request and no
caller to inherit a store from, so it builds its own from configuration — and a
worker pointed at a different database will extract books that nobody can read.
"""

from __future__ import annotations

from .queue import build_app

app = build_app()
