"""Which voice this process serves, chosen once from configuration.

Until now the composition root hardcoded :class:`DevelopmentAdapter`, so running
the reader against the real checkpoint meant editing source. That is why the
interface still played a tone even though ``XttsAdapter`` had been validated
against the bundle: the model worked, but nothing could ask for it.

Three decisions are worth stating.

**The default is the placeholder, and that is a safe default rather than a
timid one.** A tone can never be mistaken for narration — ``is_real_model``
travels with it through the response header, the manifest, the readiness report
and the cache key — so defaulting to it costs nothing. Defaulting to the real
model would cost a great deal: every test run, every CI job and every
``uvicorn --reload`` would try to load 5.6 GB from a path that usually is not
there. This is the opposite of :mod:`.security`, which fails *closed*, and for
the opposite reason: there, the unconfigured state is dangerous.

**An unrecognised value is an error, never a fallback.** CLAUDE.md forbids
silently falling back to another voice. A typo in a deployment variable must
stop the process, not quietly serve tones to a reader who was promised speech.

**Loading happens in the background at start-up, not on the first request.** The
checkpoint takes 66-112 seconds to load on this hardware. A reader who presses
play and waits ninety seconds has been failed regardless of what happens next,
so the process warms itself while readiness honestly reports that it is not
ready yet.
"""

from __future__ import annotations

import logging
import os
import threading

from sinhala_tts.adapter import DevelopmentAdapter, ReadinessState, TtsAdapter, XttsAdapter

log = logging.getLogger(__name__)

#: Which adapter to serve. See :data:`MODES`.
ADAPTER_ENV = "SINHALA_READER_TTS"

#: Force a device for the real model: ``cpu`` or ``cuda``. Unset means choose.
#: On a 4 GB card, ``cpu`` avoids an out-of-memory attempt that would fall back
#: to CPU anyway, and saves the time spent discovering that.
DEVICE_ENV = "SINHALA_READER_TTS_DEVICE"

DEVELOPMENT = "development"
XTTS = "xtts"
MODES = (DEVELOPMENT, XTTS)


def adapter_mode() -> str:
    """The configured mode, defaulting to the labelled placeholder."""
    return os.environ.get(ADAPTER_ENV, "").strip().lower() or DEVELOPMENT


def build_adapter() -> TtsAdapter:
    """Build the adapter this process will serve.

    Raises:
        ValueError: if the mode is not one of :data:`MODES`. Deliberately fatal.
    """
    mode = adapter_mode()
    if mode == DEVELOPMENT:
        return DevelopmentAdapter()
    if mode == XTTS:
        device = os.environ.get(DEVICE_ENV, "").strip().lower() or None
        # The bundle location is the TTS package's own setting
        # (SINHALA_TTS_MODEL_DIR); this module does not restate it, so there is
        # one place a model path is configured rather than two that can differ.
        return XttsAdapter(device=device)
    raise ValueError(
        f"{ADAPTER_ENV}={mode!r} is not a voice this server knows. Use one of: {', '.join(MODES)}."
    )


def warm(adapter: TtsAdapter) -> threading.Thread | None:
    """Load the model in the background, if there is one to load.

    Returns the thread so a caller can wait for it; nothing in the request path
    does. A failure here is logged and left in the adapter's own state, where
    ``/readiness`` reports it — raising on a background thread would take the
    process down without telling anyone why.
    """
    if not adapter.is_real_model:
        return None

    def _load() -> None:
        try:
            adapter.load()
        except Exception:  # noqa: BLE001 - readiness is the reporting channel
            log.exception("the voice failed to load; readiness will say so")

    thread = threading.Thread(target=_load, name="tts-warm-up", daemon=True)
    thread.start()
    return thread


def loaded_model_version(adapter: TtsAdapter) -> str | None:
    """The model version, but only once there is a loaded model to describe.

    ``TtsAdapter.model_version`` loads the bundle if it has not been loaded,
    because a cache key must describe the model that would actually generate the
    audio. That is right for the synthesis path and wrong for a health check: a
    readiness probe that blocks for ninety seconds gets killed by whatever is
    probing it, and would then be reported as an outage rather than a cold start.

    The states that may answer are listed positively rather than by exclusion.
    A deny-list would let a state added later — a failed load, a reload in
    progress — fall through to the blocking path, which is exactly the bug this
    exists to prevent.
    """
    if not adapter.is_real_model:
        return None
    if adapter.readiness not in (ReadinessState.READY, ReadinessState.DEGRADED):
        return None
    return adapter.model_version
