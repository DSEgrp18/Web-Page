"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { strings } from "@/lib/strings";
import type { IssuedReset, JoinedClass, MemberDetail, TaughtClass } from "@/lib/types";

function isTaught(room: TaughtClass | JoinedClass): room is TaughtClass {
  return "join_code" in room;
}

/**
 * One class. Its teacher sees the code to give out and the students who asked
 * to join, by name and standing only, with a way to let each in or take them
 * out. A student sees where they stand. Anyone else is told it is not found.
 *
 * The students are a table with a caption, so a screen reader can move by
 * row and hear each student's name before the buttons that act on them.
 */
export function ClassDetail({ classId }: { classId: string }) {
  const { api } = useReader();
  const { say } = useAnnouncer();
  const router = useRouter();
  const [room, setRoom] = useState<TaughtClass | JoinedClass | null>(null);
  const [missing, setMissing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const { setFailure, notice } = useFailure();
  const deleteButton = useRef<HTMLButtonElement>(null);
  const [resetFor, setResetFor] = useState<MemberDetail | null>(null);
  const [issued, setIssued] = useState<IssuedReset | null>(null);
  /** The row's button that asked for a code: where focus goes back to. */
  const resetReturn = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const found = await api.getClass(classId);
        if (!cancelled) setRoom(found);
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.kind === "not_found") setMissing(true);
        else setFailure(explain(error, {}));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, classId, setFailure]);

  async function act(work: () => Promise<TaughtClass | void>, said: string) {
    try {
      const next = await work();
      if (next) setRoom(next);
      say(said);
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }

  async function reset(member: MemberDetail) {
    try {
      setIssued(await api.issueReset(classId, member.user_id));
      say(strings.resetIssued(member.display_name));
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }

  if (missing) {
    return (
      <div className="account-page">
        <h1>{strings.errorNotFound}</h1>
        <p>
          <Link href="/classes">{strings.backToClasses}</Link>
        </p>
      </div>
    );
  }
  if (room === null) {
    return (
      <p className="hint" aria-busy="true">
        {strings.pageLoading}
      </p>
    );
  }

  return (
    <div className="account-page">
      <p>
        <Link href="/classes">{strings.backToClasses}</Link>
      </p>
      <h1>{room.name}</h1>
      {notice}

      {!isTaught(room) ? (
        <section className="account-section card" aria-labelledby="standing">
          <h2 id="standing">{strings.memberState(room.state)}</h2>
          <p>{strings.teacherOf(room.teacher_name)}</p>
        </section>
      ) : (
        <>
          <section className="account-section card" aria-labelledby="code-heading">
            <h2 id="code-heading">{strings.classCodeHeading}</h2>
            <p className="recovery-code latin" translate="no">
              {room.join_code.slice(0, 4)} {room.join_code.slice(4)}
            </p>
            <p className="hint">{strings.classCodeHint}</p>
            <div className="notice-actions">
              <button
                className="btn"
                type="button"
                onClick={() => void act(() => api.newJoinCode(classId), strings.newCodeDone)}
              >
                {strings.newCodeAction}
              </button>
            </div>
          </section>

          {issued ? (
            <IssuedCode
              issued={issued}
              onDone={() => {
                setIssued(null);
                resetReturn.current?.focus();
              }}
            />
          ) : null}

          <Members
            room={room}
            act={act}
            onReset={(member, button) => {
              resetReturn.current = button;
              setResetFor(member);
            }}
          />
          <ConfirmDialog
            open={resetFor !== null}
            title={strings.resetConfirmTitle(resetFor?.display_name ?? "")}
            body={strings.resetConfirmBody}
            cancelLabel={strings.deleteConfirmCancel}
            confirmLabel={strings.resetConfirmAction}
            onCancel={() => setResetFor(null)}
            onConfirm={() => {
              const member = resetFor;
              setResetFor(null);
              if (member) void reset(member);
            }}
            returnFocusRef={resetReturn}
          />

          <RenameClass
            room={room}
            onRename={(name) => act(() => api.renameClass(classId, name), strings.classRenamed)}
          />

          <section className="account-section card" aria-labelledby="delete-class">
            <h2 id="delete-class">{strings.deleteClassAction}</h2>
            <p>{strings.deleteClassConfirmBody}</p>
            <div className="notice-actions">
              <button
                ref={deleteButton}
                className="btn btn-danger"
                type="button"
                onClick={() => setConfirming(true)}
              >
                {strings.deleteClassAction}
              </button>
            </div>
            <ConfirmDialog
              open={confirming}
              title={strings.deleteClassConfirmTitle}
              body={strings.deleteClassConfirmBody}
              cancelLabel={strings.deleteConfirmCancel}
              confirmLabel={strings.deleteClassAction}
              onCancel={() => setConfirming(false)}
              onConfirm={() => {
                setConfirming(false);
                void act(() => api.deleteClass(classId), strings.classDeleted).then(() =>
                  router.replace("/classes"),
                );
              }}
              returnFocusRef={deleteButton}
            />
          </section>
        </>
      )}
    </div>
  );
}

/**
 * A student's new recovery code, shown once, with focus on its heading so a
 * screen reader starts there. It stays until the teacher says they are done.
 */
function IssuedCode({ issued, onDone }: { issued: IssuedReset; onDone: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const id = useId();

  useEffect(() => {
    heading.current?.focus();
  }, [issued]);

  return (
    <section className="account-section card" aria-labelledby={id}>
      <h2 id={id} ref={heading} tabIndex={-1}>
        {strings.resetCodeHeading(issued.display_name)}
      </h2>
      <p>{strings.resetCodeIntro}</p>
      <p className="recovery-code latin" translate="no">
        {issued.recovery_code}
      </p>
      <div className="notice-actions">
        <button className="btn btn-primary" type="button" onClick={onDone}>
          {strings.resetDone}
        </button>
      </div>
    </section>
  );
}

function Members({
  room,
  act,
  onReset,
}: {
  room: TaughtClass;
  act: (work: () => Promise<TaughtClass | void>, said: string) => Promise<void>;
  onReset: (member: MemberDetail, button: HTMLButtonElement) => void;
}) {
  const { api } = useReader();
  const shown = room.members.filter((m) => m.state !== "removed");
  return (
    <section className="account-section card" aria-labelledby="members-heading">
      <h2 id="members-heading">{strings.membersHeading}</h2>
      {shown.length === 0 ? (
        <p>{strings.noMembers}</p>
      ) : (
        <table className="member-table">
          <caption className="visually-hidden">{strings.membersHeading}</caption>
          <thead>
            <tr>
              <th scope="col">{strings.memberColName}</th>
              <th scope="col">{strings.memberColState}</th>
              <th scope="col">{strings.memberColShares}</th>
              <th scope="col">{strings.memberColActions}</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((member) => (
              <tr key={member.user_id}>
                <th scope="row">{member.display_name}</th>
                <td>{strings.memberState(member.state)}</td>
                <td>{member.share_progress ? strings.yes : strings.no}</td>
                <td>
                  <div className="notice-actions">
                    {member.state === "pending" ? (
                      <button
                        className="btn btn-primary btn-sm"
                        type="button"
                        onClick={() =>
                          void act(
                            () => api.setMember(room.class_id, member.user_id, "approve"),
                            strings.memberApproved(member.display_name),
                          )
                        }
                      >
                        {strings.approveNamed(member.display_name)}
                      </button>
                    ) : (
                      <button
                        className="btn btn-sm"
                        type="button"
                        onClick={(event) => onReset(member, event.currentTarget)}
                      >
                        {strings.resetNamed(member.display_name)}
                      </button>
                    )}
                    <button
                      className="btn btn-quiet btn-sm"
                      type="button"
                      onClick={() =>
                        void act(
                          () => api.setMember(room.class_id, member.user_id, "remove"),
                          strings.memberRemoved(member.display_name),
                        )
                      }
                    >
                      {strings.removeNamed(member.display_name)}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function RenameClass({ room, onRename }: { room: TaughtClass; onRename: (name: string) => void }) {
  const [name, setName] = useState(room.name);
  const id = useId();
  return (
    <section className="account-section card" aria-labelledby="rename-class">
      <h2 id="rename-class">{strings.renameClassLabel}</h2>
      <form
        className="account-fields"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          if (name.trim()) onRename(name.trim());
        }}
        noValidate
      >
        <div className="field">
          <label htmlFor={id}>{strings.renameClassLabel}</label>
          <input
            id={id}
            name="class-name"
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <button className="btn" type="submit">
          {strings.renameClassAction}
        </button>
      </form>
    </section>
  );
}
