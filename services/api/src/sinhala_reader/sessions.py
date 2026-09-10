"""Issuing and checking session tokens.

A token is 32 random bytes from ``secrets.token_urlsafe`` — 256 bits, which is
not guessable and not enumerable. Only its SHA-256 is stored, so a leaked
database does not hand over working sessions and the server has no reason to be
able to reconstruct one.

SHA-256 is the right hash *here* and the wrong hash for a password. The
difference is entropy: there is no dictionary of likely session tokens to try,
so slowing the hash down would cost a tenth of a second on every authenticated
request and buy nothing. Passwords are the opposite case and use scrypt. See
:mod:`.passwords`.

Expiry is decided in one place, :func:`live_session`, rather than in each
store. "Expired" and "never existed" must not drift apart between two
implementations, and the caller must not be able to forget the check.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from .storage import Session, Store, User

#: How long a session lasts without being renewed.
#:
#: Fourteen days is a deliberate compromise for who this is for. A student
#: revising over a term should not be made to log in every morning: signing in
#: is a much heavier task with a screen reader or at 400% zoom than it is for
#: someone who can see a form, and a short expiry taxes exactly the readers this
#: exists to serve. Sessions are revocable server-side, which is what makes a
#: long life defensible.
SESSION_LIFETIME = timedelta(days=14)

#: Renew when this much of the life is gone, so a daily reader is never logged
#: out mid-chapter. Renewing on every request would write to the database on
#: every request for no benefit.
RENEW_AFTER = timedelta(days=1)

#: 32 bytes, not 16. This is the credential; there is no reason to be frugal.
TOKEN_BYTES = 32


def new_token() -> str:
    """A fresh session token. **Returned once, to the caller, and never stored.**"""
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_hash(token: str) -> str:
    """What is stored and looked up. Never reversible to the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start(store: Store, user: User, *, now: datetime | None = None) -> tuple[str, Session]:
    """Log a user in. Returns the token to hand back, and the stored session."""
    moment = now or datetime.now(UTC)
    token = new_token()
    session = store.put_session(
        Session(
            token_hash=token_hash(token),
            user_id=user.user_id,
            created_at=moment.isoformat(),
            expires_at=(moment + SESSION_LIFETIME).isoformat(),
        )
    )
    return token, session


def live_session(store: Store, token: str, *, now: datetime | None = None) -> Session | None:
    """The session this token names, if it exists and has not expired.

    An expired session is **deleted** rather than merely refused. Otherwise a
    database accumulates dead credentials that are one clock error away from
    working again.
    """
    moment = now or datetime.now(UTC)
    stored = store.get_session(token_hash(token))
    if stored is None:
        return None

    try:
        expires = datetime.fromisoformat(stored.expires_at)
    except ValueError:
        # An unparseable expiry is treated as expired. A row that cannot be
        # understood must not be honoured as a credential.
        store.delete_session(stored.token_hash)
        return None

    if expires <= moment:
        store.delete_session(stored.token_hash)
        return None
    return stored


def renew_if_stale(store: Store, session: Session, *, now: datetime | None = None) -> Session:
    """Extend a session that has been in use, without touching a fresh one."""
    moment = now or datetime.now(UTC)
    try:
        expires = datetime.fromisoformat(session.expires_at)
    except ValueError:
        return session

    if expires - moment > SESSION_LIFETIME - RENEW_AFTER:
        return session
    return store.put_session(
        Session(
            token_hash=session.token_hash,
            user_id=session.user_id,
            created_at=session.created_at,
            expires_at=(moment + SESSION_LIFETIME).isoformat(),
        )
    )
