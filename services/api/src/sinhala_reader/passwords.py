"""Password hashing, and the two different jobs a hash does here.

**Passwords are hashed with scrypt**, deliberately slowly. A password is
low-entropy and chosen by a person, so the only defence once a database leaks is
making each guess expensive. ``hashlib.scrypt`` is memory-hard and in the
standard library, which matters for a project two other people have to be able
to run without solving a build problem first.

**Session tokens are hashed with SHA-256**, deliberately quickly, in
:mod:`.sessions`. That is not an inconsistency. A session token is 256 bits from
``secrets.token_urlsafe``, so there is nothing to guess and no dictionary to
try; the hash exists only so that a leaked database does not hand over working
sessions. Running scrypt on every authenticated request would cost a tenth of a
second per request and buy nothing.

Getting those two the wrong way round is the classic mistake, so both are
written down here.

The alternative to scrypt is Argon2id, which OWASP lists first. It is a better
algorithm and it is a dependency; scrypt with adequate parameters is explicitly
acceptable, and the standard library has it. If Argon2 arrives later,
``verify()`` already reports when a stored hash needs upgrading, so existing
passwords can be migrated on next login rather than reset.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

#: scrypt cost. OWASP lists several equivalent-work configurations for scrypt;
#: this is the one with the smallest memory footprint, measured on the
#: development machine:
#:
#:     N=2^17 r=8 p=1    895 ms    128 MB   <- the one usually quoted
#:     N=2^16 r=8 p=2    848 ms     64 MB
#:     N=2^15 r=8 p=3    649 ms     32 MB
#:     N=2^14 r=8 p=5    545 ms     16 MB   <- chosen
#:
#: Same work class, an eighth of the memory. That matters because every login
#: attempt costs this, including the failed ones: at 128 MB, eight simultaneous
#: attempts is a gigabyte, and refusing service to readers is a cheaper attack
#: than cracking anything.
#:
#: **Not configurable through the environment, deliberately.** A setting that
#: weakens password hashing is one typo away from a database of cheap hashes,
#: and nothing about a running server would look wrong. Tests lower it by
#: patching these constants, which cannot happen by accident in a deployment.
SCRYPT_LOG_N = 14
SCRYPT_R = 8
SCRYPT_P = 5

#: 16 bytes is the usual salt size, and it is per-password: two readers who
#: choose the same password must not produce the same hash, or cracking one
#: cracks both and the database reveals which accounts share a password.
SALT_BYTES = 16
KEY_BYTES = 32

#: Stored as "scrypt$<logN>$<r>$<p>$<salt>$<key>". Self-describing, so a hash
#: made with today's parameters is still verifiable after they are raised.
PREFIX = "scrypt"

#: Minimum length. Not a complexity rule: length is what helps, and the usual
#: "one capital and one symbol" rules push people towards `Password1!` while
#: making the field hostile to anyone typing with a screen reader on a phone.
MIN_LENGTH = 10

#: What this module was written to use. Reported by ``/readiness`` when the
#: running values are cheaper, so a server that is hashing weakly says so
#: rather than looking healthy.
DEFAULT_PARAMETERS = (14, 8, 5)


class WeakPassword(ValueError):
    """The password is too short to be worth hashing."""


def hash_password(password: str) -> str:
    """Hash a password for storage. Never store or log the input."""
    if len(password) < MIN_LENGTH:
        raise WeakPassword(f"A password needs at least {MIN_LENGTH} characters.")

    salt = secrets.token_bytes(SALT_BYTES)
    key = _derive(password, salt, SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P)
    return "$".join(
        [
            PREFIX,
            str(SCRYPT_LOG_N),
            str(SCRYPT_R),
            str(SCRYPT_P),
            _encode(salt),
            _encode(key),
        ]
    )


def verify(password: str, stored: str) -> tuple[bool, bool]:
    """Check a password. Returns (correct, should be rehashed).

    A malformed or unrecognised stored value is *wrong*, not an error: a row
    corrupted or written by some future scheme must fail a login rather than
    crash a route and tell the caller which account it was.

    The comparison is constant-time. A byte-by-byte comparison leaks how much of
    the derived key matched through timing, which over many attempts is enough
    to reconstruct it.
    """
    try:
        prefix, log_n, r, p, salt, key = stored.split("$")
        if prefix != PREFIX:
            return False, False
        expected = _decode(key)
        candidate = _derive(password, _decode(salt), int(log_n), int(r), int(p))
    except (ValueError, TypeError):
        return False, False

    correct = hmac.compare_digest(candidate, expected)
    outdated = (int(log_n), int(r), int(p)) != (SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P)
    return correct, correct and outdated


def is_weakened() -> bool:
    """Is this process hashing more cheaply than the module was written for?

    True only when a test has lowered the cost. ``/readiness`` reports it, so a
    server that somehow ran with a test's settings cannot look healthy.
    """
    return _work(SCRYPT_LOG_N, SCRYPT_R, SCRYPT_P) < _work(*DEFAULT_PARAMETERS)


def _work(log_n: int, r: int, p: int) -> int:
    """Roughly how much scrypt has to do. Compares configurations, not seconds."""
    return (2**log_n) * r * p


def _derive(password: str, salt: bytes, log_n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**log_n,
        r=r,
        p=p,
        dklen=KEY_BYTES,
        # scrypt's memory use is roughly 128 * N * r, and CPython refuses to go
        # past OpenSSL's default limit unless told. Without this, these
        # parameters raise "memory limit exceeded" rather than hashing. The
        # headroom is for verifying hashes made with heavier settings, which
        # must keep working after the parameters change.
        maxmem=192 * 1024 * 1024,
    )


def _encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(encoded + padding)
