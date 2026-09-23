"""How often anyone may try: signing in, recovering, asking, uploading.

A refusal is 429 with ``Retry-After``, and the same words for every limit.
There is no CAPTCHA, and these tests are part of why none is needed.
"""

from __future__ import annotations

import pytest
from conftest import as_reader, build_pdf, sinhala_page, upload
from fastapi.testclient import TestClient
from test_accounts import GOOD_PASSWORD, register

from sinhala_reader import Deps, create_app, passwords, ratelimit
from sinhala_reader.ratelimit import (
    LIMITS,
    TOO_MANY,
    Limit,
    MemoryLimiter,
    build_rate_limiter,
    client_address,
)
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import InMemoryStore


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "SCRYPT_LOG_N", 8)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    import sinhala_reader.accounts as accounts

    monkeypatch.setattr(accounts, "_ABSENT_ACCOUNT_HASH", None)


@pytest.fixture
def small_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every limit at 2, so a test reaches it in three requests."""
    monkeypatch.setattr(ratelimit, "LIMITS", {k: Limit(2, v.seconds) for k, v in LIMITS.items()})


def _client(clock: _Clock | None = None) -> TestClient:
    limiter = MemoryLimiter(clock) if clock else MemoryLimiter()
    return TestClient(
        create_app(
            Deps(
                store=InMemoryStore(),
                run_in_background=False,
                warm_on_start=False,
                rate_limiter=limiter,
            )
        )
    )


class TestTheLimiter:
    def test_allows_up_to_the_limit_and_says_when_to_come_back(self) -> None:
        clock = _Clock()
        limiter = MemoryLimiter(clock)
        allowed = [limiter.hit("register", "1.2.3.4").allowed for _ in range(5)]

        refused = limiter.hit("register", "1.2.3.4")

        assert allowed == [True] * 5
        assert not refused.allowed
        assert refused.retry_after == LIMITS["register"].seconds

    def test_a_new_window_starts_afresh(self) -> None:
        clock = _Clock()
        limiter = MemoryLimiter(clock)
        for _ in range(6):
            limiter.hit("register", "1.2.3.4")

        clock.now += LIMITS["register"].seconds

        assert limiter.hit("register", "1.2.3.4").allowed

    def test_counts_each_key_and_bucket_apart(self) -> None:
        limiter = MemoryLimiter(_Clock())
        for _ in range(6):
            limiter.hit("register", "1.2.3.4")

        assert limiter.hit("register", "5.6.7.8").allowed
        assert limiter.hit("login-ip", "1.2.3.4").allowed

    def test_an_unknown_mode_is_fatal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Not quietly unlimited."""
        monkeypatch.setenv(ratelimit.RATE_LIMIT_ENV, "none")
        with pytest.raises(ValueError, match="must be one of"):
            build_rate_limiter()

    def test_redis_without_an_address_is_fatal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ratelimit.RATE_LIMIT_ENV, "redis")
        monkeypatch.delenv("SINHALA_READER_REDIS_URL", raising=False)
        with pytest.raises(ValueError, match="REDIS_URL"):
            build_rate_limiter()

    def test_an_email_is_never_a_key_as_typed(self) -> None:
        key = ratelimit.private(" Nimali@Example.LK ")
        assert "nimali" not in key
        assert key == ratelimit.private("nimali@example.lk")


class TestTheAddress:
    def _request(self, forwarded: str | None, host: str = "10.0.0.2"):
        from starlette.requests import Request

        headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded else []
        return Request({"type": "http", "headers": headers, "client": (host, 1234)})

    def test_the_header_is_ignored_unless_trusted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Otherwise every guess could claim a fresh address and a fresh limit."""
        monkeypatch.delenv(ratelimit.TRUST_FORWARDED_ENV, raising=False)
        assert client_address(self._request("203.0.113.9")) == "10.0.0.2"

    def test_behind_the_pass_through_the_readers_address_counts(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ratelimit.TRUST_FORWARDED_ENV, "1")
        assert client_address(self._request("203.0.113.9")) == "203.0.113.9"


@pytest.mark.usefixtures("small_limits")
class TestAccountsAreLimited:
    @pytest.fixture(autouse=True)
    def sessions(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(AUTH_MODE_ENV, "sessions")

    def test_signing_in_is_refused_with_retry_after(self) -> None:
        client = _client()
        register(client)
        attempts = [
            client.post("/auth/login", json={"email": "nimali@example.lk", "password": "wrong"})
            for _ in range(3)
        ]

        assert [a.status_code for a in attempts] == [401, 401, 429]
        assert attempts[-1].json()["detail"] == TOO_MANY
        assert int(attempts[-1].headers["Retry-After"]) > 0

    def test_even_the_right_password_waits_once_limited(self) -> None:
        """Or the limit would only slow the guesses that fail."""
        client = _client()
        register(client)
        for _ in range(2):
            client.post("/auth/login", json={"email": "nimali@example.lk", "password": "wrong"})

        right = client.post(
            "/auth/login", json={"email": "nimali@example.lk", "password": GOOD_PASSWORD}
        )

        assert right.status_code == 429

    def test_an_address_with_no_account_is_limited_the_same(self) -> None:
        """So the limit is not a way to find out who has an account."""
        client = _client()
        codes = [
            client.post(
                "/auth/login", json={"email": "nobody@example.lk", "password": "wrong"}
            ).status_code
            for _ in range(3)
        ]
        assert codes == [401, 401, 429]

    def test_registration_is_limited(self) -> None:
        client = _client()
        codes = [register(client, email=f"r{i}@example.lk").status_code for i in range(3)]
        assert codes == [201, 201, 429]

    def test_recovery_is_limited(self) -> None:
        client = _client()
        codes = [
            client.post(
                "/auth/recover",
                json={
                    "email": "nimali@example.lk",
                    "recovery_code": "AAAA-BBBB-CCCC-DDDD",
                    "new_password": "a-brand-new-password",
                },
            ).status_code
            for _ in range(3)
        ]
        assert codes == [401, 401, 429]


@pytest.mark.usefixtures("small_limits")
class TestCostlyWorkIsLimited:
    @pytest.fixture(autouse=True)
    def development(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(AUTH_MODE_ENV, "development")

    def test_uploads_are_limited_per_reader(self) -> None:
        client = _client()
        pdf = build_pdf([sinhala_page()])

        codes = [upload(client, pdf).status_code for _ in range(3)]
        other = upload(client, pdf, owner="someone-else").status_code

        assert codes == [202, 202, 429]
        assert other == 202

    def test_questions_are_limited_per_reader(self) -> None:
        client = _client()
        document_id = upload(client, build_pdf([sinhala_page()])).json()["document_id"]

        codes = [
            client.post(
                f"/documents/{document_id}/questions",
                json={"question": "පොත"},
                headers=as_reader(client),
            ).status_code
            for _ in range(3)
        ]

        assert codes[:2] != [429, 429]
        assert codes[2] == 429

    def test_another_readers_book_is_absent_not_limited(self) -> None:
        client = _client()
        document_id = upload(client, build_pdf([sinhala_page()])).json()["document_id"]

        codes = {
            client.post(
                f"/documents/{document_id}/questions",
                json={"question": "පොත"},
                headers=as_reader(client, "someone-else"),
            ).status_code
            for _ in range(4)
        }

        assert codes == {404}
