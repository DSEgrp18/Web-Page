"""How often anyone may try something that is costly, or worth guessing at.

Chosen by ``SINHALA_READER_RATE_LIMIT``, like every other adapter:

``memory`` (the default)
    Counted in this process. Correct for one API process; with several, each
    allows the whole limit, and ``/readiness`` says so.

``redis``
    Counted in Redis at ``SINHALA_READER_REDIS_URL``, shared by every process.

An unknown value is fatal at start-up rather than quietly unlimited.

A refusal is 429 with ``Retry-After``. **There is no CAPTCHA,** and there will
not be one: a CAPTCHA is a test of sight or of hearing that the readers this
service is for are the most likely to fail (WCAG 2.2, 3.3.8).

The windows are fixed rather than sliding. A reader can at worst make twice a
limit across a window boundary, which is well inside what these limits are for:
stopping password guessing and runaway cost, not metering a fair user.

Keys that would identify a person (an email address) are hashed before they
are used, so Redis never holds a list of who tried to sign in.
"""

from __future__ import annotations

import hashlib
import math
import os
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

RATE_LIMIT_ENV = "SINHALA_READER_RATE_LIMIT"
MEMORY = "memory"
REDIS = "redis"
MODES = (MEMORY, REDIS)

#: Set to "1" when the API runs behind the web app's pass-through, which
#: writes the reader's address into ``X-Forwarded-For``. Off, the connecting
#: address is used; behind a proxy that is the proxy's, and every reader shares
#: one limit.
TRUST_FORWARDED_ENV = "SINHALA_READER_TRUST_FORWARDED"


@dataclass(frozen=True)
class Limit:
    count: int
    seconds: int


#: The limits, by what is being limited. See the product plan, section 6.4.
LIMITS: dict[str, Limit] = {
    # Per address, whether or not it has an account, so the limit says nothing.
    "login-email": Limit(10, 15 * 60),
    "login-ip": Limit(30, 15 * 60),
    "register": Limit(5, 60 * 60),
    "recover": Limit(10, 60 * 60),
    "invite": Limit(10, 60 * 60),
    "join": Limit(10, 60 * 60),
    # Per teacher: a class's worth of lost codes in an hour, not a sweep.
    "teacher-reset": Limit(30, 60 * 60),
    "question": Limit(60, 60 * 60),
    "upload": Limit(30, 24 * 60 * 60),
}

#: What a reader is told. The same for every bucket: which limit was reached
#: is not the business of whoever is guessing.
TOO_MANY = "Too many attempts. Wait a little and try again."


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int
    """Seconds until the window ends. Zero when allowed."""


class RateLimiter(ABC):
    @abstractmethod
    def hit(self, bucket: str, key: str) -> Decision:
        """Count one attempt, and say whether it is within the limit."""

    def limitations(self) -> list[str]:
        return []


class MemoryLimiter(RateLimiter):
    """Fixed windows, in a dictionary, in this process."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str], tuple[float, int]] = {}

    def hit(self, bucket: str, key: str) -> Decision:
        limit = LIMITS[bucket]
        now = self._clock()
        with self._lock:
            started, count = self._windows.get((bucket, key), (now, 0))
            if now - started >= limit.seconds:
                started, count = now, 0
            count += 1
            self._windows[(bucket, key)] = (started, count)
            if len(self._windows) > 100_000:
                self._forget_expired(now)
        if count <= limit.count:
            return Decision(True, 0)
        return Decision(False, max(1, math.ceil(started + limit.seconds - now)))

    def _forget_expired(self, now: float) -> None:
        for window, (started, _) in list(self._windows.items()):
            if now - started >= LIMITS[window[0]].seconds:
                del self._windows[window]

    def limitations(self) -> list[str]:
        return [
            "Rate limits are counted in this process. With more than one API process, "
            f"each allows the whole limit; set {RATE_LIMIT_ENV}={REDIS} to share them."
        ]


class RedisLimiter(RateLimiter):
    """Fixed windows in Redis: one counter per bucket and key, expiring."""

    def __init__(self, url: str) -> None:
        import redis  # only needed in this mode

        self._redis = redis.Redis.from_url(url)

    def hit(self, bucket: str, key: str) -> Decision:
        limit = LIMITS[bucket]
        name = f"swara:rl:{bucket}:{key}"
        pipe = self._redis.pipeline()
        pipe.incr(name)
        pipe.expire(name, limit.seconds, nx=True)
        pipe.ttl(name)
        count, _, ttl = pipe.execute()
        if int(count) <= limit.count:
            return Decision(True, 0)
        return Decision(False, max(1, int(ttl)))


def rate_limit_mode() -> str:
    return os.environ.get(RATE_LIMIT_ENV, "").strip() or MEMORY


def build_rate_limiter() -> RateLimiter:
    mode = rate_limit_mode()
    if mode == MEMORY:
        return MemoryLimiter()
    if mode == REDIS:
        from .queue import REDIS_URL_ENV

        url = os.environ.get(REDIS_URL_ENV, "").strip()
        if not url:
            raise ValueError(f"{RATE_LIMIT_ENV}={REDIS} needs {REDIS_URL_ENV}.")
        return RedisLimiter(url)
    raise ValueError(f"{RATE_LIMIT_ENV} must be one of {', '.join(MODES)}, not {mode!r}.")


def private(value: str) -> str:
    """A key for something that identifies a person, such as an email address."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:32]


def client_address(request: Request) -> str:
    """Who is connecting, as far as can be told.

    Behind the web app's pass-through, the connecting address is the web
    server's, so the reader's own comes from ``X-Forwarded-For``, trusted only
    when configured: otherwise anyone could send the header and pick a fresh
    limit for every guess. The pass-through replaces the header rather than
    appending to it, so its value is one address.
    """
    if os.environ.get(TRUST_FORWARDED_ENV) == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last
    return request.client.host if request.client else "unknown"


def enforce(request: Request, bucket: str, key: str) -> None:
    """Count an attempt, or refuse it with 429 and ``Retry-After``."""
    limiter: RateLimiter = request.app.state.deps.rate_limiter
    decision = limiter.hit(bucket, key)
    if not decision.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            TOO_MANY,
            headers={"Retry-After": str(decision.retry_after)},
        )
