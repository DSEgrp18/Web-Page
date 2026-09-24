"""Classes: a teacher's group of students, and a student's place in one.

A teacher makes a class and gives out its eight-digit code. A student who types
the code asks to join, and waits: the teacher approving them is the real
defence, since a code can be guessed or passed on and a teacher knows their
own students. Removal takes effect on the next request.

What a teacher sees of a student is their display name and their membership,
nothing else: never an email address, never a book, a bookmark or a question.
Whether the teacher sees progress is the student's choice, off until they make
it, and theirs to withdraw.

Every read is scoped in the store to the class's teacher or the member, and
anything else is absent (404), as for documents.

A teacher can also make a reset code for one of their own students, for a
student who has lost both their password and their recovery code. It lasts
thirty minutes, works once, and sits beside the student's own code rather than
replacing it. It changes nothing by itself: the student spends it on the
recovery page with their own email address, which the teacher never sees, and
is told afterwards, on every screen until they acknowledge it, who made it.
"""

from __future__ import annotations

import secrets
from dataclasses import replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from .. import codes
from ..accounts import RECOVERY_GROUPS, TEACHER_RESET_LIFETIME
from ..ratelimit import enforce
from ..security import require_user
from ..storage import (
    AuditEvent,
    Classroom,
    CodeTaken,
    Membership,
    MemberState,
    Role,
    TeacherReset,
    User,
    new_id,
)

if TYPE_CHECKING:
    from ..app import Deps

CODE_DIGITS = 8

#: The signed-in account, injected; hoisted, as in accounts.py.
CurrentUser = Depends(require_user)

NO_CLASS = "No such class."
NO_CODE = "No class has that code."


def new_join_code() -> str:
    """Eight digits: the easiest code to type on a phone keypad or hear read aloud."""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_DIGITS))


def normalise_code(code: str) -> str:
    """Only the digits count, so "1234 5678" and "1234-5678" both work."""
    return "".join(character for character in code if character.isdigit())


# -- bodies and answers -----------------------------------------------------


class ClassBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A class needs a name.")
        return value


class JoinBody(BaseModel):
    code: str = Field(min_length=1, max_length=32)


class ShareBody(BaseModel):
    share: bool


class MemberDetail(BaseModel):
    """A student as their teacher sees them: a name and a standing, no more."""

    user_id: str
    display_name: str
    state: str = Field(description="pending, active or removed.")
    share_progress: bool
    joined_at: str


class TaughtClass(BaseModel):
    class_id: str
    name: str
    join_code: str
    created_at: str
    members: list[MemberDetail] = Field(default_factory=list)


class JoinedClass(BaseModel):
    """A class as its student sees it. No code: that is the teacher's to share."""

    class_id: str
    name: str
    teacher_name: str
    state: str = Field(description="pending or active.")
    share_progress: bool


class IssuedReset(BaseModel):
    """A reset code for a student, for their teacher to hand over. Shown once."""

    display_name: str
    recovery_code: str
    expires_at: str


class MyClasses(BaseModel):
    teaching: list[TaughtClass]
    joined: list[JoinedClass]


def register(app: FastAPI, deps: Deps) -> None:
    """Add the class routes to ``app``, acting through ``deps``."""
    store = deps.store

    def name_of(user_id: str) -> str:
        user = store.get_user(user_id)
        return user.display_name if user else ""

    def taught(class_id: str, teacher: User) -> Classroom:
        found = store.class_taught(class_id, teacher.user_id)
        if found is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASS)
        return found

    def taught_detail(classroom: Classroom) -> TaughtClass:
        return TaughtClass(
            class_id=classroom.class_id,
            name=classroom.name,
            join_code=classroom.join_code,
            created_at=classroom.created_at,
            members=[
                MemberDetail(
                    user_id=m.user_id,
                    display_name=name_of(m.user_id),
                    state=str(m.state),
                    share_progress=m.share_progress,
                    joined_at=m.joined_at,
                )
                for m in store.members(classroom.class_id, classroom.teacher_id)
            ],
        )

    def joined_detail(classroom: Classroom, membership: Membership) -> JoinedClass:
        return JoinedClass(
            class_id=classroom.class_id,
            name=classroom.name,
            teacher_name=name_of(classroom.teacher_id),
            state=str(membership.state),
            share_progress=membership.share_progress,
        )

    def audit(actor: str, subject: str, kind: str, reason: str) -> None:
        store.record(
            AuditEvent(
                event_id=new_id("aud"), kind=kind, actor=actor, subject=subject, reason=reason
            )
        )

    # -- everyone ------------------------------------------------------------

    @app.get("/classes", tags=["classes"])
    def my_classes(user: User = CurrentUser) -> MyClasses:
        """The classes this account teaches, and the ones it belongs to."""
        return MyClasses(
            teaching=[taught_detail(c) for c in store.classes_taught(user.user_id)],
            joined=[joined_detail(c, m) for c, m in store.classes_joined(user.user_id)],
        )

    @app.post("/classes/join", tags=["classes"])
    def join(body: JoinBody, request: Request, user: User = CurrentUser) -> JoinedClass:
        """Ask to join a class with its code. The teacher still has to approve.

        Limited per account, and every wrong code gets the same answer, so the
        route is no quicker a way to find classes than guessing blind.
        """
        enforce(request, "join", user.user_id)
        classroom = store.class_by_code(normalise_code(body.code))
        if classroom is None or classroom.teacher_id == user.user_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CODE)
        membership = store.join_class(classroom.class_id, user.user_id)
        return joined_detail(classroom, membership)

    @app.put("/classes/{class_id}/share-progress", tags=["classes"])
    def share_progress(class_id: str, body: ShareBody, user: User = CurrentUser) -> JoinedClass:
        """The student's own choice to let the teacher see their progress."""
        if not store.set_share_progress(class_id, user.user_id, body.share):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASS)
        for classroom, membership in store.classes_joined(user.user_id):
            if classroom.class_id == class_id:
                return joined_detail(classroom, membership)
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASS)

    @app.delete(
        "/classes/{class_id}/membership",
        status_code=status.HTTP_204_NO_CONTENT,
        tags=["classes"],
    )
    def leave(class_id: str, user: User = CurrentUser) -> Response:
        """Leave a class. Nothing of the student's stays behind in it."""
        if not store.leave_class(class_id, user.user_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASS)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # -- teachers ------------------------------------------------------------

    @app.post("/classes", status_code=status.HTTP_201_CREATED, tags=["classes"])
    def create_class(body: ClassBody, user: User = CurrentUser) -> TaughtClass:
        """Make a class. Teachers only: nobody becomes a teacher by making one."""
        if user.role is not Role.TEACHER:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a teacher can make a class.")
        for _ in range(10):
            try:
                classroom = store.put_class(
                    Classroom(
                        class_id=new_id("cls"),
                        teacher_id=user.user_id,
                        name=body.name,
                        join_code=new_join_code(),
                    )
                )
                return taught_detail(classroom)
            except CodeTaken:
                continue  # a hundred million codes; a clash is rare, ten is absurd
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not make a code. Try again."
        )

    @app.get("/classes/{class_id}", tags=["classes"])
    def get_class(class_id: str, user: User = CurrentUser) -> TaughtClass | JoinedClass:
        """A class, as its teacher or its member sees it; absent to anyone else."""
        classroom = store.class_taught(class_id, user.user_id)
        if classroom is not None:
            return taught_detail(classroom)
        for joined, membership in store.classes_joined(user.user_id):
            if joined.class_id == class_id:
                return joined_detail(joined, membership)
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASS)

    @app.patch("/classes/{class_id}", tags=["classes"])
    def rename_class(class_id: str, body: ClassBody, user: User = CurrentUser) -> TaughtClass:
        classroom = taught(class_id, user)
        return taught_detail(store.put_class(replace(classroom, name=body.name)))

    @app.post("/classes/{class_id}/code", tags=["classes"])
    def new_code(class_id: str, user: User = CurrentUser) -> TaughtClass:
        """Replace the join code, for one that has been passed around too far.

        Members already in the class stay in; the old code stops working.
        """
        taught(class_id, user)
        for _ in range(10):
            try:
                store.set_join_code(class_id, user.user_id, new_join_code())
                return taught_detail(taught(class_id, user))
            except CodeTaken:
                continue
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Could not make a code. Try again."
        )

    @app.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["classes"])
    def delete_class(class_id: str, user: User = CurrentUser) -> Response:
        """Delete the class and every membership in it. Students' own books are untouched."""
        if not store.delete_class(class_id, user.user_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, NO_CLASS)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    def set_state(class_id: str, member_id: str, teacher: User, state: MemberState) -> TaughtClass:
        classroom = taught(class_id, teacher)
        if not store.set_member_state(class_id, teacher.user_id, member_id, state):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member.")
        audit(teacher.user_id, member_id, f"member_{state}", f"class:{class_id}")
        return taught_detail(classroom)

    @app.post("/classes/{class_id}/members/{member_id}/approve", tags=["classes"])
    def approve(class_id: str, member_id: str, user: User = CurrentUser) -> TaughtClass:
        """Let a student in. Recorded, since it grants access to the class's books."""
        return set_state(class_id, member_id, user, MemberState.ACTIVE)

    @app.post("/classes/{class_id}/members/{member_id}/remove", tags=["classes"])
    def remove(class_id: str, member_id: str, user: User = CurrentUser) -> TaughtClass:
        """Take a student out. Their access ends on their next request."""
        return set_state(class_id, member_id, user, MemberState.REMOVED)

    @app.post("/classes/{class_id}/members/{member_id}/reset", tags=["classes"])
    def issue_reset(
        class_id: str, member_id: str, request: Request, user: User = CurrentUser
    ) -> IssuedReset:
        """Make a thirty-minute, single-use reset code for an approved student.

        It changes no password and leaves the student's own recovery code as it
        was: the student uses it on the recovery page, with their own email
        address, to choose a new password. A second one replaces the first.
        Only for students: an account that is itself a teacher's holds other
        people's classes, and is reset by an admin. Recorded in the audit log,
        and the student is told.
        """
        enforce(request, "teacher-reset", user.user_id)
        taught(class_id, user)
        membership = store.membership(class_id, member_id)
        student = store.get_user(member_id)
        if (
            membership is None
            or membership.state != MemberState.ACTIVE
            or student is None
            or student.role != Role.STUDENT
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No such member.")
        code = codes.new_code(RECOVERY_GROUPS)
        issued = datetime.now(UTC)
        reset = store.put_teacher_reset(
            TeacherReset(
                user_id=student.user_id,
                code_hash=codes.code_hash(code),
                issued_by=user.user_id,
                issued_at=issued.isoformat(),
                expires_at=(issued + TEACHER_RESET_LIFETIME).isoformat(),
            )
        )
        audit(user.user_id, student.user_id, "teacher_reset_issued", f"class:{class_id}")
        return IssuedReset(
            display_name=student.display_name, recovery_code=code, expires_at=reset.expires_at
        )
