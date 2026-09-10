"""Who is asking.

Two modes, chosen by ``SINHALA_READER_AUTH``, and the server refuses to serve
private documents under neither:

``sessions``
    Real accounts. ``Authorization: Bearer <token>`` from ``POST /auth/login``,
    checked against a stored session. This is the mode a deployment uses.

``development``
    The ``X-Reader-User`` header, trusted completely. **Anyone can claim to be
    anyone.** It exists because the reader interface and the whole document
    pipeline can be built and reviewed without accounts, and because Kusal and
    Lasana should not need a database and a registered user to check a focus
    order. ``/readiness`` reports it as a limitation on every call.

Unset is neither, and every request is refused. A deployment that forgets to
configure authentication fails closed and loudly rather than serving private
books to whoever asks.

The shape has not changed since header identity: every request resolves to an
owner, and every store operation takes that owner and enforces it. That was the
part worth getting right first — it runs through the store, the cache, the
audio and the deletion path — and it is why this file is the only one that
changed when real credentials arrived.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException, Request, status

from . import sessions
from .storage import Store, User

#: Header carrying the caller's identity in development mode only.
OWNER_HEADER = "X-Reader-User"

#: Which authentication scheme is in use. Unset means none, and none means the
#: API refuses every request.
AUTH_MODE_ENV = "SINHALA_READER_AUTH"

DEVELOPMENT_MODE = "development"
SESSIONS_MODE = "sessions"
MODES = (SESSIONS_MODE, DEVELOPMENT_MODE)

_UNCONFIGURED = (
    "This server has no authentication configured, so it will not serve private "
    f"documents. Set {AUTH_MODE_ENV}=sessions for real accounts, or "
    f"{AUTH_MODE_ENV}=development for local use only."
)

#: Deliberately identical for "no such account", "wrong password", "expired
#: session" and "token that was never issued". Telling them apart tells an
#: attacker which addresses have accounts here — and for a reader with a
#: disability, membership of this service is not something to leak.
NOT_SIGNED_IN = "Sign in to continue."


def auth_mode() -> str:
    return os.environ.get(AUTH_MODE_ENV, "")


def is_development_auth() -> bool:
    return auth_mode() == DEVELOPMENT_MODE


def uses_sessions() -> bool:
    return auth_mode() == SESSIONS_MODE


def store_of(request: Request) -> Store:
    return request.app.state.deps.store


def require_owner(
    request: Request,
    x_reader_user: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
) -> str:
    """Resolve the caller to an owner id, or refuse.

    Returns the value every store method is scoped by. In development that is
    whatever the caller typed; in sessions mode it is a user id that a password
    was checked for.
    """
    if uses_sessions():
        return _from_session(store_of(request), authorization).user_id

    if is_development_auth():
        if not x_reader_user or not x_reader_user.strip():
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                f"Send your identity in the {OWNER_HEADER} header.",
            )
        return x_reader_user.strip()

    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNCONFIGURED)


def require_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> User:
    """The signed-in account itself, for the routes that need more than an id.

    Only available in sessions mode: in development there is no account behind
    the header, and inventing one would make the placeholder look real.
    """
    if not uses_sessions():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"This server has no accounts. Set {AUTH_MODE_ENV}=sessions.",
        )
    store = store_of(request)
    session = _from_session(store, authorization)
    user = store.get_user(session.user_id)
    if user is None:
        # The account went while the session lived. End the session rather than
        # leave a credential pointing at nobody.
        store.delete_session(session.token_hash)
        raise _unauthorised()
    return user


def _from_session(store: Store, authorization: str | None):
    token = _bearer(authorization)
    if token is None:
        raise _unauthorised()
    session = sessions.live_session(store, token)
    if session is None:
        raise _unauthorised()
    return sessions.renew_if_stale(store, session)


def _bearer(authorization: str | None) -> str | None:
    """The token out of an Authorization header, if there is one.

    The scheme is compared case-insensitively because RFC 7235 says it is
    case-insensitive, and a client sending "bearer" is not making a mistake
    worth refusing a reader over.
    """
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


def _unauthorised() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        NOT_SIGNED_IN,
        # Names the scheme so a client knows what to send. Carries no detail
        # about why, deliberately.
        headers={"WWW-Authenticate": "Bearer"},
    )


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
