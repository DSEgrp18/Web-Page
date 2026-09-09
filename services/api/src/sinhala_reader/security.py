"""Who is asking. **This is not real authentication.**

The reader has no accounts, no sessions and no password handling yet, and
inventing them here would be worse than leaving the gap visible. What exists
instead is the *shape* authorisation will keep: every request resolves to an
owner, and every store operation takes that owner and enforces it.

That ordering is deliberate. Ownership enforcement is the part that is expensive
to retrofit — it has to run through the store, the cache, the audio, and the
deletion path — and it is the part CLAUDE.md requires to be tested. Swapping a
header for a verified session token later touches one function.

Until then the identity comes from a request header and is trusted completely.
Anyone can claim to be anyone. It is safe only on a machine nobody else can
reach, which is why :func:`require_owner` refuses to run when the app is not
explicitly in development mode.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, status

#: Header carrying the caller's identity. Replaced by a verified credential.
OWNER_HEADER = "X-Reader-User"

#: Must be set to "development" for header identity to be accepted. Without it
#: the API refuses every request rather than serving private documents to
#: whoever asks — a deployment that forgets to configure real authentication
#: fails closed and loudly.
AUTH_MODE_ENV = "SINHALA_READER_AUTH"

DEVELOPMENT_MODE = "development"

_UNCONFIGURED = (
    "This server has no authentication configured, so it will not serve private "
    "documents. Set SINHALA_READER_AUTH=development for local use only; a deployment "
    "needs real credentials, which are not implemented yet."
)


def auth_mode() -> str:
    return os.environ.get(AUTH_MODE_ENV, "")


def is_development_auth() -> bool:
    return auth_mode() == DEVELOPMENT_MODE


def require_owner(x_reader_user: str | None = Header(default=None)) -> str:
    """Resolve the caller, or refuse.

    Fails closed twice over: once when no authentication scheme is configured at
    all, and again when the caller supplies no identity. Neither failure leaks
    whether a document exists.
    """
    if not is_development_auth():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNCONFIGURED)
    if not x_reader_user or not x_reader_user.strip():
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            f"Send your identity in the {OWNER_HEADER} header.",
        )
    return x_reader_user.strip()


#: Comma-separated origins the browser reader is served from, e.g.
#: "http://localhost:3000". Empty means no browser may call this API at all.
ORIGINS_ENV = "SINHALA_READER_ORIGINS"


def allowed_origins() -> list[str]:
    """Origins permitted to call this API from a browser.

    Fails closed, like everything else here: unset means no cross-origin access,
    not "any". A wildcard has to be typed out deliberately, and ``/readiness``
    reports it as a limitation when it is.

    The reader UI runs on a different origin from the API — a separate Next.js
    process in development, and a separate host in deployment — so without this
    the browser refuses every request before it is sent, and the interface can
    only report that it is offline.
    """
    raw = os.environ.get(ORIGINS_ENV, "")
    return [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
