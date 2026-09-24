"""Liveness, and readiness with every way this deployment is not production."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI
from sinhala_tts.adapter import ReadinessState
from sinhala_tts.adapter import health as adapter_health

from .. import passwords
from ..adapters import ADAPTER_ENV, adapter_mode, loaded_model_version
from ..answers import answer_limitations, answers_mode
from ..queue import QUEUE_ENV, REDIS_URL_ENV, queue_mode, uses_celery
from ..recognition import ocr_limitations, ocr_mode
from ..security import (
    AUTH_MODE_ENV,
    allowed_origins,
    auth_mode,
    is_development_auth,
    uses_sessions,
)
from ..storage import DATABASE_URL_ENV, is_durable
from ..structure import structure_limitations, structure_mode

if TYPE_CHECKING:
    from ..app import Deps


def register(app: FastAPI, deps: Deps) -> None:
    """Add the operations routes to ``app``, acting through ``deps``."""
    origins = allowed_origins()

    # -- health ------------------------------------------------------------

    @app.get("/health", tags=["operations"])
    def health() -> dict:
        """Liveness. Says nothing about whether a model is loaded."""
        return {"alive": True}

    @app.get("/readiness", tags=["operations"])
    def readiness() -> dict:
        """Readiness, and every way this deployment is not production.

        CLAUDE.md requires liveness and model readiness to be separate, and
        requires unenforced or missing pieces to be reported honestly rather
        than implied by silence.
        """
        report = adapter_health(deps.adapter)
        limitations = list(report.notes)
        if not deps.adapter.is_real_model:
            limitations.append(
                "Audio is a placeholder tone, not speech. It must not be used as narration. "
                f"Set {ADAPTER_ENV}=xtts to serve the real voice."
            )
        elif report.readiness in (ReadinessState.NOT_LOADED, ReadinessState.LOADING):
            # A cold start, not a fault. Said plainly so an operator waits
            # rather than restarting the process and starting the load again.
            limitations.append(
                "The voice is still loading and cannot narrate yet. This takes over a "
                "minute from cold; it is not a failure."
            )
        elif report.readiness is ReadinessState.FAILED:
            # This one *is* a fault, and it has to be said. Without it a server
            # whose voice is dead reports a state string and four unrelated
            # notes, and reads as healthy to anyone skimming.
            limitations.append(
                "The voice failed to load, so nothing can be narrated. "
                + (report.detail or "No reason was recorded.")
            )
        if not uses_celery():
            limitations.append(
                "Preparation runs in a thread. Work in flight is lost if this process "
                f"stops, and its job stays 'running' for ever. Set {QUEUE_ENV}=celery "
                f"and {REDIS_URL_ENV} for a durable queue."
            )
        if not is_durable(deps.store):
            limitations.append(
                "Storage is in memory. Documents, audio and reading positions are lost "
                f"when this process stops. Set {DATABASE_URL_ENV} to use PostgreSQL."
            )
        if is_development_auth():
            limitations.append(
                "Authentication is a trusted header. Anyone can claim to be anyone; "
                f"do not expose this server. Set {AUTH_MODE_ENV}=sessions for accounts."
            )
        elif uses_sessions():
            # Accounts exist, and these are the ways they are still not
            # finished. Saying nothing here would let "we have logins" stand in
            # for "this is safe to expose".
            limitations.append(
                "There is no email verification. A forgotten password is reset with the "
                "recovery code shown once at registration; a reader who has lost both "
                "needs an admin."
            )
            if passwords.is_weakened():
                limitations.append(
                    "Passwords are being hashed more cheaply than this build intends. "
                    "This should only ever happen in tests."
                )
        if not is_development_auth() and not uses_sessions():
            limitations.append(
                f"No authentication is configured, so every request is refused. "
                f"Set {AUTH_MODE_ENV} to one of: sessions, development."
            )
        # No origins is the normal case now: the web app reaches this API through
        # its own /api pass-through, so no browser calls it cross-origin. Only a
        # wildcard is worth a warning.
        if "*" in origins:
            limitations.append(
                "Any website may call this API from a browser. With header identity that "
                "means any page can read any reader's documents."
            )
        limitations.extend(deps.rate_limiter.limitations())
        limitations.extend(structure_limitations())
        limitations.extend(ocr_limitations())
        limitations.extend(answer_limitations())
        return {
            "alive": report.alive,
            "serving": report.serving,
            "readiness": report.readiness,
            "structure": structure_mode(),
            "ocr": ocr_mode().value,
            "answers": answers_mode(),
            "real_model": deps.adapter.is_real_model,
            # Not `adapter.model_version`: that loads the bundle if it has not
            # been loaded, and a readiness probe that blocks for a minute and a
            # half gets killed and reported as an outage rather than a cold start.
            "model_version": loaded_model_version(deps.adapter),
            "voice": adapter_mode(),
            "device": report.device,
            "voice_detail": report.detail,
            "auth_mode": auth_mode() or "unconfigured",
            "queue": queue_mode(),
            "limitations": limitations,
        }
