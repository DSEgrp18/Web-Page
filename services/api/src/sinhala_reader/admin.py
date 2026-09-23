"""The admin command line. Where every admin action happens.

An admin has no screens and no access to anyone's content. Making a teacher,
or a teacher invitation, is done here, by someone with shell access to the
deployment and its database, and every action is written to the audit log::

    python -m sinhala_reader.admin grant-role --email t@school.lk --role teacher \\
        --reason verified-teacher
    python -m sinhala_reader.admin invite-teacher --days 7
    python -m sinhala_reader.admin issue-reset --email s@school.lk --reason lost-code
    python -m sinhala_reader.admin list-audit --email s@school.lk

Reasons are codes from a fixed list, never free text, so the log can be read
and counted without anyone having typed something private into it.

It needs ``SINHALA_READER_DATABASE_URL``. Against the in-memory store a grant
would be forgotten the moment the command ends, which is worse than an error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

from . import codes
from .accounts import RECOVERY_GROUPS
from .storage import (
    AuditEvent,
    Role,
    Store,
    TeacherInvite,
    build_store,
    is_durable,
    new_id,
)

#: Why a role was granted or taken away. Extend the list rather than typing
#: something else: the log is only useful if it can be counted.
REASONS = ("verified-teacher", "school-staff", "correction", "revoked")

#: Why an admin gave someone a new recovery code.
RESET_REASONS = ("lost-code", "lost-password-and-code", "identity-checked-in-person")

#: Longest an invitation may live. A code in a message thread is a code
#: anyone who later reads the thread can use.
MAX_INVITE_DAYS = 30

ACTOR = "cli"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m sinhala_reader.admin")
    commands = parser.add_subparsers(dest="command", required=True)

    grant = commands.add_parser("grant-role", help="Make an account a student, teacher or admin.")
    grant.add_argument("--email", required=True)
    grant.add_argument("--role", required=True, choices=[str(r) for r in Role])
    grant.add_argument("--reason", required=True, choices=REASONS)

    invite = commands.add_parser(
        "invite-teacher", help="Print a single-use code that makes a student a teacher."
    )
    invite.add_argument("--days", type=int, default=7)

    reset = commands.add_parser(
        "issue-reset",
        help="Print a new recovery code for an account. The last resort, after the "
        "reader's own code and their teacher.",
    )
    reset.add_argument("--email", required=True)
    reset.add_argument("--reason", required=True, choices=RESET_REASONS)

    audit = commands.add_parser("list-audit", help="What has changed an account's access.")
    audit.add_argument("--email", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    store: Store | None = None,
    out: Callable[[str], None] = print,
) -> int:
    args = _parser().parse_args(argv)
    if store is None:
        store = build_store()
        if not is_durable(store):
            out(
                "No database is configured (SINHALA_READER_DATABASE_URL). "
                "Against the in-memory store this would be forgotten at once."
            )
            return 2

    if args.command == "grant-role":
        return _grant_role(store, args.email, Role(args.role), args.reason, out)
    if args.command == "issue-reset":
        return _issue_reset(store, args.email, args.reason, out)
    if args.command == "list-audit":
        return _list_audit(store, args.email, out)
    return _invite_teacher(store, args.days, out)


def _grant_role(
    store: Store, email: str, role: Role, reason: str, out: Callable[[str], None]
) -> int:
    user = store.get_user_by_email(email.strip().lower())
    if user is None:
        out("No account has that email address.")
        return 1
    if user.role is role:
        out(f"{user.email} is already a {role}. Nothing changed.")
        return 0

    store.set_role(user.user_id, role)
    store.record(
        AuditEvent(
            event_id=new_id("aud"),
            kind="role_granted",
            actor=ACTOR,
            subject=user.user_id,
            reason=f"{user.role}->{role}:{reason}",
        )
    )
    out(f"{user.email} is now a {role}.")
    return 0


def _issue_reset(store: Store, email: str, reason: str, out: Callable[[str], None]) -> int:
    """A new recovery code, printed once, replacing the account's old one.

    It changes no password and ends no session by itself: the reader spends it
    at "recover", which does both. So a code read out to the wrong person on
    the phone still needs them to know the account's address.
    """
    user = store.get_user_by_email(email.strip().lower())
    if user is None:
        out("No account has that email address.")
        return 1
    code = codes.new_code(RECOVERY_GROUPS)
    store.set_recovery_hash(user.user_id, codes.code_hash(code))
    store.record(
        AuditEvent(
            event_id=new_id("aud"),
            kind="recovery_code_issued",
            actor=ACTOR,
            subject=user.user_id,
            reason=reason,
        )
    )
    out(f"Recovery code for {user.email}: {code}")
    out("It replaces their old code. They use it on the recovery page to set a new password.")
    return 0


def _list_audit(store: Store, email: str, out: Callable[[str], None]) -> int:
    user = store.get_user_by_email(email.strip().lower())
    if user is None:
        out("No account has that email address.")
        return 1
    events = store.audit_for(user.user_id)
    if not events:
        out(f"Nothing recorded for {user.email}.")
    for event in events:
        out(f"{event.at}  {event.kind}  by {event.actor}  {event.reason}")
    return 0


def _invite_teacher(store: Store, days: int, out: Callable[[str], None]) -> int:
    if not 1 <= days <= MAX_INVITE_DAYS:
        out(f"--days must be between 1 and {MAX_INVITE_DAYS}.")
        return 1

    now = datetime.now(UTC)
    code = codes.new_code()
    expires_at = (now + timedelta(days=days)).isoformat()
    store.put_invite(
        TeacherInvite(
            code_hash=codes.code_hash(code),
            created_by=ACTOR,
            created_at=now.isoformat(),
            expires_at=expires_at,
        )
    )
    store.record(
        AuditEvent(
            event_id=new_id("aud"),
            kind="invite_created",
            actor=ACTOR,
            subject=None,
            reason=f"teacher:{days}d",
        )
    )
    # Printed once and stored nowhere: only its hash is kept.
    out(f"Teacher invitation: {code}")
    out(f"Single use. It expires at {expires_at}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
