"""Register, sign in, sign out, and change a password.

Four routes, and most of the care in them is about **what they refuse to say**.

A login that answers "no such account" for one address and "wrong password" for
another has told an attacker which addresses have accounts. Here that is not an
abstract leak: this service is for blind and low-vision readers and students,
and membership of it is information about a person's disability. So every
failure to sign in is the same answer, in the same shape, and takes roughly the
same time.

The one place that deliberately does say more is registration, which has to tell
a reader that an address is already registered — otherwise the only way to
discover it is to fail to sign in. That is the standard trade, and it is a real
trade rather than an oversight: it makes addresses enumerable through this
route, which is why it belongs behind a rate limit before this is public. There
is no rate limiting yet, and ``/readiness`` says so.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator

from . import passwords, sessions
from .security import AUTH_MODE_ENV, NOT_SIGNED_IN, require_user, store_of, uses_sessions
from .storage import EmailTaken, Store, User, new_id

router = APIRouter(prefix="/auth", tags=["accounts"])

#: A failed login should not be measurably faster than a successful one. When
#: there is no account, there is no stored hash to check, so the work that makes
#: a real login slow never happens and the response comes back sooner — which
#: says "no account here" without saying it.
#:
#: So a missing account verifies against a real hash of a throwaway password and
#: discards the answer. Comparing against a *constant* dummy hash would be
#: cheaper but is computed once at import, and both branches must do the same
#: kind of work rather than merely take a similar time.
_ABSENT_ACCOUNT_HASH: str | None = None


def _dummy_hash() -> str:
    global _ABSENT_ACCOUNT_HASH
    if _ABSENT_ACCOUNT_HASH is None:
        _ABSENT_ACCOUNT_HASH = passwords.hash_password("x" * passwords.MIN_LENGTH)
    return _ABSENT_ACCOUNT_HASH


class Email(BaseModel):
    """An email field, checked only for the shape of one.

    Deliberately not ``pydantic.EmailStr``: that needs the ``email-validator``
    package, and full RFC validation would still not establish that the address
    exists or belongs to the person typing it. The only thing that establishes
    that is sending mail to it, which this service does not do yet — so the
    check here is the minimum that catches a typo, and no more is claimed.
    """

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def _looks_like_an_address(cls, value: str) -> str:
        value = value.strip()
        local, at, domain = value.partition("@")
        if not at or not local or not domain or " " in value or "." not in domain:
            raise ValueError("That does not look like an email address.")
        return value


class Registration(Email):
    password: str = Field(min_length=passwords.MIN_LENGTH, max_length=1024)
    display_name: str = Field(min_length=1, max_length=100)


class Credentials(Email):
    password: str = Field(max_length=1024)
    """No minimum here.

    A length rule on the login form would refuse an old password that was set
    before the rule existed, and would answer differently for a short password
    than for a wrong one — which is the leak this module exists to avoid.
    """


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(min_length=passwords.MIN_LENGTH, max_length=1024)


class Account(BaseModel):
    """What a reader is told about themselves. Never the hash, never the token."""

    user_id: str
    email: str
    display_name: str
    created_at: str

    @classmethod
    def of(cls, user: User) -> Account:
        return cls(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            created_at=user.created_at,
        )


class SignedIn(BaseModel):
    """The token, returned exactly once. It is not stored anywhere in this shape."""

    token: str
    expires_at: str
    account: Account


def sessions_or_503() -> None:
    if not uses_sessions():
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"This server has no accounts. Set {AUTH_MODE_ENV}=sessions.",
        )


SessionsRequired = Depends(sessions_or_503)

#: The signed-in account, injected. Hoisted out of the argument defaults so the
#: Depends() call happens once at import rather than on every call.
CurrentUser = Depends(require_user)


@router.post("/register", status_code=status.HTTP_201_CREATED, dependencies=[SessionsRequired])
def register(body: Registration, request: Request) -> SignedIn:
    """Create an account and sign in with it.

    Signing in immediately is not a convenience. Making a reader who has just
    chosen a password type it again, on a screen reader or at 400% zoom, is a
    real cost for no security gain.
    """
    store = store_of(request)
    email = body.email.strip()

    try:
        password_hash = passwords.hash_password(body.password)
    except passwords.WeakPassword as weak:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(weak)) from weak

    user = User(
        user_id=new_id("usr"),
        email=email,
        email_key=email.lower(),
        password_hash=password_hash,
        display_name=body.display_name.strip(),
    )
    try:
        store.put_user(user)
    except EmailTaken as taken:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That email address already has an account.",
        ) from taken

    return _sign_in(store, user)


@router.post("/login", dependencies=[SessionsRequired])
def login(body: Credentials, request: Request) -> SignedIn:
    """Sign in. Every failure is the same failure."""
    store = store_of(request)
    user = store.get_user_by_email(body.email.strip().lower())

    # Both branches run a real scrypt verification, so the response time does
    # not depend on whether the address is registered.
    stored_hash = user.password_hash if user else _dummy_hash()
    correct, needs_rehash = passwords.verify(body.password, stored_hash)

    if not correct or user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, NOT_SIGNED_IN)

    if needs_rehash:
        # The parameters were raised since this password was set. Upgrade it
        # now, while the plaintext is in hand, rather than resetting it later.
        user = User(
            user_id=user.user_id,
            email=user.email,
            email_key=user.email_key,
            password_hash=passwords.hash_password(body.password),
            display_name=user.display_name,
            created_at=user.created_at,
        )
        store.put_user(user)

    return _sign_in(store, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SessionsRequired])
def logout(request: Request) -> None:
    """End this session. Idempotent, and never says whether it found one.

    A reader pressing "sign out" twice, or after their session expired, must get
    the same calm answer both times — and an unauthenticated caller must not be
    able to use this route to find out whether a token is live.
    """
    store = store_of(request)
    token = _token_of(request)
    if token:
        store.delete_session(sessions.token_hash(token))


@router.get("/me")
def me(user: User = CurrentUser) -> Account:
    """Who am I. The route a reloaded interface uses to find out it is signed in."""
    return Account.of(user)


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(body: PasswordChange, request: Request, user: User = CurrentUser) -> None:
    """Change a password and end every session, including this one.

    Ending them is the point. A password changed because someone else may know
    it has not been changed at all if their session keeps working — and the
    reader who just changed it believes they are safe.
    """
    store = store_of(request)

    correct, _ = passwords.verify(body.current_password, user.password_hash)
    if not correct:
        # The current password is required precisely because a session might be
        # stolen: without it, whoever holds the token can lock the reader out of
        # their own account.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That password is not correct.")

    try:
        password_hash = passwords.hash_password(body.new_password)
    except passwords.WeakPassword as weak:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(weak)) from weak

    store.put_user(
        User(
            user_id=user.user_id,
            email=user.email,
            email_key=user.email_key,
            password_hash=password_hash,
            display_name=user.display_name,
            created_at=user.created_at,
        )
    )
    store.delete_sessions_for_user(user.user_id)


def _sign_in(store: Store, user: User) -> SignedIn:
    token, session = sessions.start(store, user)
    return SignedIn(token=token, expires_at=session.expires_at, account=Account.of(user))


def _token_of(request: Request) -> str | None:
    from .security import _bearer

    return _bearer(request.headers.get("authorization"))
