"""The access matrix: who can reach which book, through every route. A release gate.

Seven actors, three books, every route that touches a document. Each cell is
either allowed, or 404. Never 403: a 403 on a real id confirms the id is real,
and these are books belonging to identifiable students.

The rule under test (CLAUDE.md, "Accounts, roles, and authorization"):

* **Reading** is allowed to a book's owner, or to an *active* member of a class
  the book is published to.
* **Writing** (rename, jobs, retry, review, publishing) is the owner's alone.
* A teacher never sees a student's private book. An admin sees no one's.

It runs against both stores, so the SQL predicate and the in-memory one are
held to the same table.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import pytest
from conftest import build_pdf, sinhala_page
from fastapi.testclient import TestClient
from test_accounts import register

from sinhala_reader import Deps, create_app, passwords
from sinhala_reader.ratelimit import Decision, RateLimiter
from sinhala_reader.security import AUTH_MODE_ENV
from sinhala_reader.storage import InMemoryStore, Role, Store

ACTORS = [
    "teacher",  # owns both teacher books; teaches classes A and B
    "active",  # an approved member of class A; owns the private book
    "pending",  # asked to join class A, not yet approved
    "removed",  # was in class A, removed by the teacher
    "other_class",  # an approved member of class B, where nothing is published
    "stranger",  # a student in no class at all
    "admin",  # an admin: no content access, by design
]

BOOKS = ["unpublished", "published", "private"]

OWNER_OF = {"unpublished": "teacher", "published": "teacher", "private": "active"}

#: (label, method, path, body, kind). ``{doc}``, ``{seg}`` and ``{job}`` are
#: filled in per book. ``read`` routes are open to active class members of a
#: published book; ``write`` routes are the owner's only.
ROUTES = [
    ("detail", "GET", "/documents/{doc}", None, "read"),
    ("page", "GET", "/documents/{doc}/pages/0", None, "read"),
    ("segment", "GET", "/documents/{doc}/segments/{seg}", None, "read"),
    ("audio", "GET", "/documents/{doc}/segments/{seg}/audio", None, "read"),
    ("manifest", "GET", "/documents/{doc}/segments/{seg}/audio/manifest", None, "read"),
    ("file", "GET", "/documents/{doc}/file", None, "read"),
    ("question", "POST", "/documents/{doc}/questions", {"question": "පොත"}, "read"),
    ("bookmarks", "GET", "/documents/{doc}/bookmarks", None, "read"),
    ("bookmark", "POST", "/documents/{doc}/bookmarks", {"segment_id": "{seg}"}, "read"),
    ("save position", "PUT", "/documents/{doc}/progress", {"segment_id": "{seg}"}, "read"),
    ("rename", "PATCH", "/documents/{doc}", {"title": "නව නම"}, "write"),
    ("job", "GET", "/documents/{doc}/jobs/{job}", None, "write"),
    ("retry", "POST", "/documents/{doc}/retry", None, "write"),
    ("review", "GET", "/documents/{doc}/review", None, "write"),
    ("publication", "GET", "/documents/{doc}/publication", None, "write"),
]


def allowed(actor: str, book: str, kind: str) -> bool:
    if actor == OWNER_OF[book]:
        return True
    return kind == "read" and book == "published" and actor == "active"


@dataclass
class World:
    client: TestClient
    headers: dict[str, dict[str, str]]
    books: dict[str, dict[str, str]]  # book -> {"doc", "seg", "job"}
    class_a: str


def _fill(template, book: dict[str, str]):
    if template is None:
        return None
    if isinstance(template, str):
        return template.format(**book)
    return {key: _fill(value, book) for key, value in template.items()}


class _NoLimits(RateLimiter):
    """The matrix is about access, not limits: seven accounts from one address
    would otherwise meet the registration limit, which has its own tests."""

    def hit(self, bucket: str, key: str) -> Decision:
        return Decision(True, 0)


def _store(kind: str) -> Store:
    if kind == "memory":
        return InMemoryStore()
    from sinhala_reader.postgres import PostgresStore, migrate

    url = os.environ["SINHALA_READER_DATABASE_URL"]
    migrate(url)
    store = PostgresStore(url)
    store.reset_for_tests()
    return store


def _build(kind: str) -> World:
    store = _store(kind)
    client = TestClient(
        create_app(
            Deps(
                store=store,
                run_in_background=False,
                warm_on_start=False,
                rate_limiter=_NoLimits(),
            )
        ),
        headers={"X-Session-Transport": "bearer"},
    )
    headers: dict[str, dict[str, str]] = {}
    ids: dict[str, str] = {}
    for actor in ACTORS:
        body = register(client, email=f"{actor}@school.lk", name=actor).json()
        headers[actor] = {"Authorization": f"Bearer {body['token']}"}
        ids[actor] = body["account"]["user_id"]
    store.set_role(ids["teacher"], Role.TEACHER)
    store.set_role(ids["admin"], Role.ADMIN)

    def made(name: str) -> dict:
        return client.post("/classes", json={"name": name}, headers=headers["teacher"]).json()

    class_a, class_b = made("A"), made("B")
    for actor, room in [("active", class_a), ("pending", class_a), ("removed", class_a),
                        ("other_class", class_b)]:  # fmt: skip
        client.post("/classes/join", json={"code": room["join_code"]}, headers=headers[actor])
    for actor, room in [("active", class_a), ("removed", class_a), ("other_class", class_b)]:
        client.post(
            f"/classes/{room['class_id']}/members/{ids[actor]}/approve",
            headers=headers["teacher"],
        )
    client.post(
        f"/classes/{class_a['class_id']}/members/{ids['removed']}/remove",
        headers=headers["teacher"],
    )

    pdf = build_pdf([sinhala_page()])
    books: dict[str, dict[str, str]] = {}
    for book in BOOKS:
        owner = headers[OWNER_OF[book]]
        detail = client.post(
            "/documents",
            files={"file": (f"{book}.pdf", pdf, "application/pdf")},
            headers=owner,
        ).json()
        doc = detail["document_id"]
        page = client.get(f"/documents/{doc}/pages/0", headers=owner).json()
        books[book] = {
            "doc": doc,
            "seg": page["segments"][0]["segment_id"],
            "job": detail["job"]["job_id"],
        }

    shared = client.post(
        f"/documents/{books['published']['doc']}/publish",
        json={"class_ids": [class_a["class_id"]], "basis": "own_work"},
        headers=headers["teacher"],
    )
    assert shared.status_code == 200, shared.text
    return World(client=client, headers=headers, books=books, class_a=class_a["class_id"])


@pytest.fixture(autouse=True)
def cheap_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(passwords, "SCRYPT_LOG_N", 8)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    import sinhala_reader.accounts as accounts

    monkeypatch.setattr(accounts, "_ABSENT_ACCOUNT_HASH", None)


@pytest.fixture(autouse=True)
def sessions_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(AUTH_MODE_ENV, "sessions")


_WORLDS: dict[str, World] = {}


@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param(
            "postgres",
            id="postgres",
            marks=pytest.mark.skipif(
                not os.environ.get("SINHALA_READER_DATABASE_URL"),
                reason="No SINHALA_READER_DATABASE_URL: the Postgres matrix did not run.",
            ),
        ),
    ]
)
def world(request: pytest.FixtureRequest, cheap_hashing, sessions_auth) -> World:
    """One world per store, built once: the matrix only reads it, and building
    it registers seven accounts and prepares three books."""
    if request.param not in _WORLDS:
        _WORLDS[request.param] = _build(request.param)
    return _WORLDS[request.param]


@pytest.mark.parametrize("route", ROUTES, ids=[route[0] for route in ROUTES])
@pytest.mark.parametrize("book", BOOKS)
@pytest.mark.parametrize("actor", ACTORS)
def test_the_matrix(world: World, actor: str, book: str, route: tuple) -> None:
    label, method, path, body, kind = route
    ids = world.books[book]

    response = world.client.request(
        method,
        _fill(path, ids),
        json=_fill(body, ids),
        headers=world.headers[actor],
    )

    if allowed(actor, book, kind):
        # Allowed need not mean 200: a retry of a book that did not fail is a
        # 409, and that is the owner being told something, not refused.
        assert response.status_code not in (401, 403, 404), (actor, book, label, response.text)
    else:
        assert response.status_code == 404, (actor, book, label, response.status_code)
