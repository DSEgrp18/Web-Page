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

import hmac
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from . import codes, passwords, sessions
from .preparation import forget_prepared
from .ratelimit import client_address, enforce, private
from .security import (
    AUTH_MODE_ENV,
    NOT_SIGNED_IN,
    clear_session_cookie,
    csrf_token,
    refuse_cross_site,
    require_user,
    session_token,
    set_session_cookie,
    store_of,
    uses_sessions,
    wants_bearer,
)
from .storage import AuditEvent, EmailTaken, Role, Store, User, new_id

#: Every account route refuses a request another site's page made. For the
#: routes a session protects, that is part of CSRF protection; for sign-in and
#: registration it stops a page signing a reader into someone else's account.
router = APIRouter(prefix="/auth", tags=["accounts"], dependencies=[Depends(refuse_cross_site)])

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


class Recovery(Email):
    recovery_code: str = Field(min_length=1, max_length=64)
    new_password: str = Field(min_length=passwords.MIN_LENGTH, max_length=1024)


class PasswordCheck(BaseModel):
    current_password: str = Field(max_length=1024)


class RecoveryCode(BaseModel):
    """A new recovery code. Shown once; only its hash is kept."""

    recovery_code: str


#: Four groups of four: about 79 bits, for a code that resets a password.
RECOVERY_GROUPS = 4

#: How long a code a teacher made for their student lasts. Long enough to
#: hand it over in class and use it; short enough that a code left on a desk
#: is worthless by the next lesson.
TEACHER_RESET_LIFETIME = timedelta(minutes=30)

#: One answer for "no such account", "no recovery code on it" and "wrong code".
RECOVERY_REFUSED = "That email address and recovery code do not match."

#: Compared against when there is no account or no code, so both branches do
#: the same work. Never a valid code's hash: it is the hash of nothing.
_NO_CODE_HASH = codes.code_hash("")


class ResetNotice(BaseModel):
    """A teacher made a reset code for this account, and the reader has not yet
    said they have seen that. Shown on every screen until they do."""

    teacher_name: str | None = Field(
        description="Null when that teacher's account has since been deleted."
    )
    issued_at: str
    used: bool


class Account(BaseModel):
    """What a reader is told about themselves. Never the hash, never the token."""

    user_id: str
    email: str
    display_name: str
    role: str = Field(description="student, teacher or admin.")
    has_recovery_code: bool = Field(
        description="False for accounts made before recovery codes, until they make one."
    )
    created_at: str

    @classmethod
    def of(cls, user: User) -> Account:
        return cls(
            user_id=user.user_id,
            email=user.email,
            display_name=user.display_name,
            role=str(user.role),
            has_recovery_code=user.recovery_hash is not None,
            created_at=user.created_at,
        )


class Invitation(BaseModel):
    code: str = Field(min_length=1, max_length=64)


#: One answer for an invitation that does not exist, has been used, or has
#: expired. Which of the three is not the typist's business.
INVALID_INVITATION = "That invitation code is not valid."


class SignedIn(BaseModel):
    """A new session. A browser receives it as a cookie, never in this body."""

    token: str | None = Field(
        default=None,
        description=(
            "Only for a client that sent X-Session-Transport: bearer, such as a test or "
            "a script. A browser gets an httpOnly cookie instead, which no script can read."
        ),
    )
    expires_at: str
    account: Account
    csrf_token: str = Field(
        description="Send back in X-CSRF-Token on every POST, PUT, PATCH and DELETE."
    )
    recovery_code: str | None = Field(
        default=None,
        description=(
            "Present only when an account is made or recovered: the one code that can "
            "reset its password. Shown once and never again."
        ),
    )


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
def register(body: Registration, request: Request, response: Response) -> SignedIn:
    """Create an account and sign in with it.

    Signing in immediately is not a convenience. Making a reader who has just
    chosen a password type it again, on a screen reader or at 400% zoom, is a
    real cost for no security gain.
    """
    enforce(request, "register", client_address(request))
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

    recovery_code = _new_recovery_code(store, user)
    # Read back, so the account says it has a code because it does.
    signed_in = _sign_in(store, store.get_user(user.user_id) or user, request, response)
    return signed_in.model_copy(update={"recovery_code": recovery_code})


@router.post("/recover", dependencies=[SessionsRequired])
def recover(body: Recovery, request: Request, response: Response) -> SignedIn:
    """Set a new password with the account's recovery code, with no email.

    There is no email here to send a reset link to, and a reader who has lost
    a password must not have lost the books with it. The code is spent: every
    session ends, as for a password change, and a new code comes back, to be
    kept in place of the old one.

    Every refusal is one answer, and takes the same work, for the reason
    ``login`` gives: whether an address has an account here is information
    about a person's disability.
    """
    enforce(request, "recover", f"ip:{client_address(request)}")
    enforce(request, "recover", f"email:{private(body.email)}")
    store = store_of(request)
    # Hashed first, and whatever happens next: the expensive step runs for a
    # wrong code as it does for a right one. A weak password is refused before
    # the code is looked at, which says nothing about the account.
    try:
        password_hash = passwords.hash_password(body.new_password)
    except passwords.WeakPassword as weak:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(weak)) from weak

    user = store.get_user_by_email(body.email.strip().lower())
    typed = codes.code_hash(body.recovery_code)
    stored = user.recovery_hash if user and user.recovery_hash else _NO_CODE_HASH
    # Compared first, and whatever happens next, as the hash above is.
    matches = hmac.compare_digest(typed, stored)
    own_code = matches and user is not None and user.recovery_hash is not None
    # Otherwise a code their teacher made, spent here or not at all. Checked
    # only when their own code did not match, so it is never spent for nothing.
    now = datetime.now(UTC).isoformat()
    teachers_code = (
        user is not None and not own_code and store.spend_teacher_reset(user.user_id, typed, now)
    )
    if user is None or not (own_code or teachers_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, RECOVERY_REFUSED)

    user = store.put_user(replace(user, password_hash=password_hash))
    store.delete_sessions_for_user(user.user_id)
    store.record(
        AuditEvent(
            event_id=new_id("aud"),
            kind="password_recovered",
            actor=user.user_id,
            subject=user.user_id,
            reason="teacher-reset" if teachers_code else "recovery-code",
        )
    )
    recovery_code = _new_recovery_code(store, user)
    # Read back, so the account says it has a code because it does.
    signed_in = _sign_in(store, store.get_user(user.user_id) or user, request, response)
    return signed_in.model_copy(update={"recovery_code": recovery_code})


@router.post("/recovery-code")
def replace_recovery_code(
    body: PasswordCheck, request: Request, user: User = CurrentUser
) -> RecoveryCode:
    """Make a new recovery code, and end the old one.

    For a reader who lost the code, or whose account predates codes. It asks
    for the password, as a password change does: whoever holds a stolen
    session must not be able to mint a code and take the account.
    """
    correct, _ = passwords.verify(body.current_password, user.password_hash)
    if not correct:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That password is not correct.")
    store = store_of(request)
    code = _new_recovery_code(store, user)
    store.record(
        AuditEvent(
            event_id=new_id("aud"),
            kind="recovery_code_replaced",
            actor=user.user_id,
            subject=user.user_id,
            reason="account-page",
        )
    )
    return RecoveryCode(recovery_code=code)


@router.get("/reset-notice")
def reset_notice(request: Request, user: User = CurrentUser) -> ResetNotice | None:
    """Whether a teacher made a reset code for this account that the reader has
    not yet been told about. Null when there is nothing to tell.

    Told whether or not the code was used: a reset the reader did not ask for
    is the one they most need to hear about, and whom to ask about it.
    """
    store = store_of(request)
    reset = store.teacher_reset(user.user_id)
    if reset is None or reset.seen_at is not None:
        return None
    teacher = store.get_user(reset.issued_by) if reset.issued_by else None
    return ResetNotice(
        teacher_name=teacher.display_name if teacher else None,
        issued_at=reset.issued_at,
        used=reset.used_at is not None,
    )


@router.post("/reset-notice/seen", status_code=status.HTTP_204_NO_CONTENT)
def reset_notice_seen(request: Request, user: User = CurrentUser) -> None:
    """The reader has read the notice. Saying so twice is harmless."""
    store_of(request).acknowledge_teacher_reset(user.user_id, datetime.now(UTC).isoformat())


@router.post("/login", dependencies=[SessionsRequired])
def login(body: Credentials, request: Request, response: Response) -> SignedIn:
    """Sign in. Every failure is the same failure.

    Limited by address and by account, before any work: per account whether
    or not it exists, so the limit is not a way to find out.
    """
    enforce(request, "login-ip", client_address(request))
    enforce(request, "login-email", private(body.email))
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
        user = store.put_user(replace(user, password_hash=passwords.hash_password(body.password)))

    return _sign_in(store, user, request, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[SessionsRequired])
def logout(request: Request, response: Response) -> None:
    """End this session. Idempotent, and never says whether it found one.

    A reader pressing "sign out" twice, or after their session expired, must get
    the same calm answer both times — and an unauthenticated caller must not be
    able to use this route to find out whether a token is live.
    """
    store = store_of(request)
    token, _ = session_token(request)
    if token:
        store.delete_session(sessions.token_hash(token))
    clear_session_cookie(response)


@router.post("/logout-everywhere", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(request: Request, response: Response, user: User = CurrentUser) -> None:
    """End every session this account has, on every device.

    For a reader who signed in on a shared or lost phone. Needs a live session
    here, and its CSRF token, like any other change to the account.
    """
    store_of(request).delete_sessions_for_user(user.user_id)
    clear_session_cookie(response)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    body: PasswordCheck, request: Request, response: Response, user: User = CurrentUser
) -> None:
    """Delete the account and everything in it. Not undoable.

    Every book goes first, each through the same deletion a reader's delete
    button uses, so its text, audio, positions, bookmarks and caches go with it.
    Then the account, its sessions and its history. It asks for the password,
    because a session left open on a shared phone must not be enough to erase
    someone's year of notes.

    Phones are shared: the web app also clears its offline audio on the way out.
    Backups are kept for the period the privacy notice states, and then go too.
    """
    correct, _ = passwords.verify(body.current_password, user.password_hash)
    if not correct:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That password is not correct.")

    store = store_of(request)
    for document in store.list_documents(user.user_id):
        store.delete_document(document.document_id, user.user_id)
        forget_prepared(document.document_id)
    store.delete_user(user.user_id)
    clear_session_cookie(response)


class Me(Account):
    csrf_token: str | None = Field(
        default=None,
        description="For a browser session: send back in X-CSRF-Token. Null for a bearer token.",
    )


@router.get("/me")
def me(request: Request, user: User = CurrentUser) -> Me:
    """Who am I. The route a reloaded interface uses to find out it is signed in.

    It also hands a reloaded page its CSRF token, which the page cannot keep:
    anything a script can store, a script injected into the page can read.
    """
    token, by_cookie = session_token(request)
    csrf = csrf_token(sessions.token_hash(token)) if token and by_cookie else None
    return Me(**Account.of(user).model_dump(), csrf_token=csrf)


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

    store.put_user(replace(user, password_hash=password_hash))
    store.delete_sessions_for_user(user.user_id)


@router.post("/teacher-invite")
def redeem_teacher_invite(body: Invitation, request: Request, user: User = CurrentUser) -> Account:
    """Become a teacher with a single-use code an admin issued.

    The only way an account makes itself a teacher, and it needs something an
    admin handed over. A teacher or admin already has the role, and is not
    allowed to spend an invitation meant for someone else.
    """
    enforce(request, "invite", user.user_id)
    store = store_of(request)
    if user.role is not Role.STUDENT:
        raise HTTPException(status.HTTP_409_CONFLICT, "This account already has that role.")

    now = datetime.now(UTC).isoformat()
    if not store.redeem_invite(codes.code_hash(body.code), user.user_id, now):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, INVALID_INVITATION)

    store.set_role(user.user_id, Role.TEACHER)
    store.record(
        AuditEvent(
            event_id=new_id("aud"),
            kind="role_granted",
            actor=user.user_id,
            subject=user.user_id,
            reason="student->teacher:invitation",
        )
    )
    return Account.of(replace(user, role=Role.TEACHER))


def _new_recovery_code(store: Store, user: User) -> str:
    """Give an account a fresh code, replacing any it had. Returns it, once."""
    code = codes.new_code(RECOVERY_GROUPS)
    store.set_recovery_hash(user.user_id, codes.code_hash(code))
    return code


def _sign_in(store: Store, user: User, request: Request, response: Response) -> SignedIn:
    """Start a session: a cookie for a browser, a token for a client that asked."""
    token, session = sessions.start(store, user)
    bearer = wants_bearer(request)
    if not bearer:
        set_session_cookie(response, token, int(sessions.SESSION_LIFETIME.total_seconds()))
    return SignedIn(
        token=token if bearer else None,
        expires_at=session.expires_at,
        account=Account.of(user),
        csrf_token=csrf_token(session.token_hash),
    )
