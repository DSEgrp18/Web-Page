"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { explain, useFailure } from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";
import type { JoinedClass, MyClasses, TaughtClass } from "@/lib/types";

/** How a standing looks: approved in green, waiting in amber. */
const STANDING_PILL = { active: "pill pill-ok", pending: "pill pill-warn" } as const;

/**
 * A reader's classes: joining one with a code, the ones they belong to, and,
 * for a teacher, the ones they teach.
 *
 * Joining asks, it does not admit: the class says "waiting" until the teacher
 * approves. The consent to share progress sits beside the code, unticked, so
 * nobody shares by not noticing a box.
 */
export function Classes() {
  const { api, account } = useReader();
  const [classes, setClasses] = useState<MyClasses | null>(null);
  const { setFailure, notice } = useFailure();

  const load = useCallback(async () => {
    try {
      setClasses(await api.myClasses());
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }, [api, setFailure]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const found = await api.myClasses();
        if (!cancelled) setClasses(found);
      } catch (error) {
        if (!cancelled) setFailure(explain(error, {}));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, setFailure]);

  return (
    <div className="account-page">
      <h1>{strings.classesHeading}</h1>
      {notice}
      <JoinForm onJoined={load} />
      {classes === null ? (
        <p className="hint" aria-busy="true">
          {strings.pageLoading}
        </p>
      ) : (
        <>
          <Joined classes={classes.joined} onChanged={load} />
          {account?.role === "teacher" ? (
            <Teaching classes={classes.teaching} onCreated={load} />
          ) : null}
        </>
      )}
    </div>
  );
}

function JoinForm({ onJoined }: { onJoined: () => Promise<void> }) {
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [code, setCode] = useState("");
  const [share, setShare] = useState(false);
  const [busy, setBusy] = useState(false);
  const codeId = useId();
  const hintId = useId();
  const shareId = useId();
  const shareHintId = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      const joined = await api.joinClass(code);
      if (share) await api.shareProgress(joined.class_id, true);
      setCode("");
      setShare(false);
      setFailure(null);
      say(strings.joinedWaiting(joined.name));
      await onJoined();
    } catch (error) {
      setFailure(explain(error, { 404: strings.errorNoClassCode }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="account-section card" aria-labelledby="join-heading">
      <h2 id="join-heading">{strings.joinHeading}</h2>
      {notice}
      <form className="account-fields" onSubmit={submit} noValidate>
        <div className="field">
          <label htmlFor={codeId}>{strings.joinCodeLabel}</label>
          <input
            id={codeId}
            name="join-code"
            inputMode="numeric"
            autoComplete="off"
            aria-describedby={hintId}
            required
            value={code}
            onChange={(event) => setCode(event.target.value)}
          />
          <p className="hint" id={hintId}>
            {strings.joinCodeHint}
          </p>
        </div>
        <div className="check-row">
          <input
            id={shareId}
            type="checkbox"
            checked={share}
            aria-describedby={shareHintId}
            onChange={(event) => setShare(event.target.checked)}
          />
          <label htmlFor={shareId}>{strings.shareProgressLabel}</label>
        </div>
        <p className="hint" id={shareHintId}>
          {strings.shareProgressHint}
        </p>
        <button className="btn btn-primary" type="submit" aria-busy={busy}>
          {strings.joinAction}
        </button>
      </form>
    </section>
  );
}

function Joined({
  classes,
  onChanged,
}: {
  classes: JoinedClass[];
  onChanged: () => Promise<void>;
}) {
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();

  async function act(work: () => Promise<unknown>, said: string) {
    try {
      await work();
      say(said);
      await onChanged();
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }

  return (
    <section className="account-section card" aria-labelledby="joined-heading">
      <h2 id="joined-heading">{strings.joinedHeading}</h2>
      {notice}
      {classes.length === 0 ? (
        <p>{strings.noJoined}</p>
      ) : (
        <ul className="class-list">
          {classes.map((room) => (
            <li key={room.class_id} className="class-item">
              <h3>{room.name}</h3>
              <p>
                {strings.teacherOf(room.teacher_name)} ·{" "}
                <span className={STANDING_PILL[room.state]}>{strings.memberState(room.state)}</span>
              </p>
              <ShareToggle
                room={room}
                onToggle={(share) =>
                  act(
                    () => api.shareProgress(room.class_id, share),
                    share ? strings.progressShared : strings.progressPrivate,
                  )
                }
              />
              <div className="notice-actions">
                <button
                  className="btn btn-quiet"
                  type="button"
                  onClick={() => void act(() => api.leaveClass(room.class_id), strings.leftClass)}
                >
                  {strings.leaveClass}
                  <span className="visually-hidden"> — {room.name}</span>
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ShareToggle({
  room,
  onToggle,
}: {
  room: JoinedClass;
  onToggle: (share: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="check-row">
      <input
        id={id}
        type="checkbox"
        checked={room.share_progress}
        onChange={(event) => onToggle(event.target.checked)}
      />
      <label htmlFor={id}>
        {strings.shareProgressLabel}
        <span className="visually-hidden"> — {room.name}</span>
      </label>
    </div>
  );
}

function Teaching({
  classes,
  onCreated,
}: {
  classes: TaughtClass[];
  onCreated: () => Promise<void>;
}) {
  const { api } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [name, setName] = useState("");
  const nameId = useId();

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      await api.createClass(name.trim());
      setName("");
      say(strings.classCreated);
      await onCreated();
    } catch (error) {
      setFailure(explain(error, {}));
    }
  }

  return (
    <section className="account-section card" aria-labelledby="teaching-heading">
      <h2 id="teaching-heading">{strings.teachingHeading}</h2>
      {notice}
      {classes.length === 0 ? (
        <p>{strings.noTaught}</p>
      ) : (
        <ul className="class-list">
          {classes.map((room) => {
            const active = room.members.filter((m) => m.state === "active").length;
            const pending = room.members.filter((m) => m.state === "pending").length;
            return (
              <li key={room.class_id} className="class-item">
                <h3>
                  <Link href={`/classes/${encodeURIComponent(room.class_id)}`}>{room.name}</Link>
                </h3>
                <p>{strings.memberCounts(active, pending)}</p>
              </li>
            );
          })}
        </ul>
      )}
      <form className="account-fields" onSubmit={create} noValidate>
        <div className="field">
          <label htmlFor={nameId}>{strings.createClassLabel}</label>
          <input
            id={nameId}
            name="class-name"
            required
            maxLength={120}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <button className="btn btn-primary" type="submit">
          {strings.createClassAction}
        </button>
      </form>
    </section>
  );
}
