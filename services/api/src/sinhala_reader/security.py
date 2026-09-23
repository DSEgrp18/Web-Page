"""Who is asking.

Two modes, chosen by ``SINHALA_READER_AUTH``, and the server refuses to serve
private documents under neither:

``sessions``
    Real accounts, checked against a stored session. This is the mode a
    deployment uses. A browser holds the session in an httpOnly cookie, which
    no script on the page can read; see "Cookies" below. Tests and scripts may
    ask for a bearer token instead.

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

Cookies
-------

The session cookie is ``__Host-swara_session``: ``HttpOnly``, so a script
running in the page (pdf.js renders untrusted PDFs there) cannot take it;
``Secure``; and ``SameSite=Lax``, not ``Strict``, because Strict signs a
student out when they follow a teacher's link from a messaging app.

A cookie is sent by the browser whoever asks, so a cookie-authenticated
request must also prove it came from this site:

* **Fetch Metadata.** A request marked ``Sec-Fetch-Site: cross-site`` or
  ``same-site`` is refused, whatever its method. GET is included because
  asking for audio starts synthesis, which costs money.
* **A CSRF token** on every POST, PUT, PATCH and DELETE: an HMAC of the
  session under ``SINHALA_READER_SECRET``, returned at sign-in and by
  ``/auth/me``, and sent back in ``X-CSRF-Token``. A page on another site can
  make the browser send the cookie; it cannot read the token.

A bearer token, which a page on another site cannot make a browser send, needs
neither.
"""

from __future__ import annotations

import hashlib
import hmac
import os

from fastapi import Header, HTTPException, Request, Response, status

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

#: The browser's session. ``__Host-`` makes the browser insist it is Secure,
#: has Path=/ and no Domain, so no other host can set or read it.
SESSION_COOKIE = "__Host-swara_session"

#: Where a cookie-authenticated request sends its CSRF token.
CSRF_HEADER = "X-CSRF-Token"

#: A client that wants a bearer token in the response body, rather than a
#: cookie, says so here. Tests and scripts do; the web app's pass-through
#: strips it, so a browser never receives a token a script could read.
TRANSPORT_HEADER = "X-Session-Transport"

#: The key the CSRF tokens are made with. At least 32 bytes, and required in
#: sessions mode: the server will not start without it.
SECRET_ENV = "SINHALA_READER_SECRET"
MIN_SECRET_BYTES = 32

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Refusals of a request that did not come from this site. Not the 404 an
#: absent resource gets: nothing about any resource is being said.
CROSS_SITE = "Requests from other sites are refused."
BAD_CSRF = "This page is out of date. Reload it and try again."

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


def session_secret() -> bytes:
    """The CSRF key. Raises when it is missing or too short to be one."""
    secret = os.environ.get(SECRET_ENV, "").encode("utf-8")
    if len(secret) < MIN_SECRET_BYTES:
        raise ValueError(
            f"{AUTH_MODE_ENV}={SESSIONS_MODE} needs {SECRET_ENV} set to at least "
            f"{MIN_SECRET_BYTES} random bytes, for example the output of "
            '`python -c "import secrets; print(secrets.token_urlsafe(48))"`.'
        )
    return secret


def check_configuration() -> None:
    """Fail at start-up, not at the first sign-in, when sessions cannot work."""
    if uses_sessions():
        session_secret()


def csrf_token(token_hash: str) -> str:
    """The CSRF token for a session: an HMAC of its stored hash."""
    return hmac.new(session_secret(), token_hash.encode("utf-8"), hashlib.sha256).hexdigest()


def refuse_cross_site(request: Request) -> None:
    """Refuse a request the browser says came from another site.

    Only the two values that mean another site. ``same-origin`` is this site,
    ``none`` is the reader typing the address, and a client that sends no
    Fetch-Metadata at all is not a browser following a hostile page.
    """
    if request.headers.get("sec-fetch-site") in ("cross-site", "same-site"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, CROSS_SITE)


def wants_bearer(request: Request) -> bool:
    return request.headers.get(TRANSPORT_HEADER, "").strip().lower() == "bearer"


def set_session_cookie(response: Response, token: str, max_age: int) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=max_age,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")


def session_token(request: Request) -> tuple[str | None, bool]:
    """The session token a request carries, and whether it came by cookie."""
    bearer = _bearer(request.headers.get("authorization"))
    if bearer is not None:
        return bearer, False
    cookie = request.cookies.get(SESSION_COOKIE)
    return (cookie, True) if cookie else (None, False)


def require_owner(
    request: Request,
    response: Response,
    x_reader_user: str | None = Header(default=None),
) -> str:
    """Resolve the caller to an owner id, or refuse.

    Returns the value every store method is scoped by. In development that is
    whatever the caller typed; in sessions mode it is a user id that a password
    was checked for.
    """
    if uses_sessions():
        return _from_session(store_of(request), request, response).user_id

    if is_development_auth():
        if not x_reader_user or not x_reader_user.strip():
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                f"Send your identity in the {OWNER_HEADER} header.",
            )
        return x_reader_user.strip()

    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _UNCONFIGURED)


def require_user(request: Request, response: Response) -> User:
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
    session = _from_session(store, request, response)
    user = store.get_user(session.user_id)
    if user is None:
        # The account went while the session lived. End the session rather than
        # leave a credential pointing at nobody.
        store.delete_session(session.token_hash)
        raise _unauthorised()
    return user


def _from_session(store: Store, request: Request, response: Response):
    token, by_cookie = session_token(request)
    if token is None:
        raise _unauthorised()
    if by_cookie:
        # Before the session is even looked up: a request from another site
        # learns nothing, not even whether the cookie it rode on is live.
        refuse_cross_site(request)
    session = sessions.live_session(store, token)
    if session is None:
        raise _unauthorised()
    if by_cookie and request.method in _UNSAFE_METHODS:
        sent = request.headers.get(CSRF_HEADER, "")
        if not hmac.compare_digest(sent, csrf_token(session.token_hash)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, BAD_CSRF)
    renewed = sessions.renew_if_stale(store, session)
    if by_cookie and renewed.expires_at != session.expires_at:
        # The server extended the session; the browser's cookie must follow,
        # or a daily reader is signed out when the first cookie runs out.
        set_session_cookie(response, token, int(sessions.SESSION_LIFETIME.total_seconds()))
    return renewed


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
