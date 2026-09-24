"use client";

import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import {
  explain,
  MIN_PASSWORD_LENGTH,
  PasswordField,
  RecoveryCode,
  useFailure,
} from "@/components/AccountForms";
import { useAnnouncer } from "@/components/Announcer";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useReader } from "@/components/ReaderProvider";
import { strings } from "@/lib/strings";

/**
 * The account page: who you are, and the four things you can do about it.
 *
 * Each action is its own section with its own heading, so a screen-reader
 * user can jump between them by heading and hear what each one does before
 * reaching its button. Everything that changes the account asks for the
 * current password, as the API does: a session left open on a shared phone
 * must not be enough to take or erase someone's account.
 */
export function AccountSettings() {
  const { account } = useReader();
  const [code, setCode] = useState<string | null>(null);
  const top = useRef<HTMLHeadingElement>(null);

  if (!account) return null;

  if (code) {
    return (
      <RecoveryCode
        email={account.email}
        code={code}
        doneLabel={strings.backToAccount}
        onDone={() => {
          setCode(null);
          // Back where the reader came from, not to the top of the page.
          queueMicrotask(() => top.current?.focus());
        }}
      />
    );
  }

  return (
    <div className="account-page">
      <h1 ref={top} tabIndex={-1}>
        {strings.accountHeading}
      </h1>

      <Section heading={strings.accountDetails}>
        <dl className="account-details">
          <dt>{strings.displayNameLabel}</dt>
          <dd>{account.display_name}</dd>
          <dt>{strings.emailLabel}</dt>
          <dd className="latin">{account.email}</dd>
          <dt>{strings.roleTerm}</dt>
          <dd>{strings.roleName(account.role)}</dd>
        </dl>
      </Section>

      <ChangePassword />
      <NewRecoveryCode missing={!account.has_recovery_code} onMade={setCode} />
      <SignOutEverywhere />
      <DeleteAccount />
    </div>
  );
}

function Section({ heading, children }: { heading: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className="account-section card" aria-labelledby={id}>
      <h2 id={id}>{heading}</h2>
      {children}
    </section>
  );
}

function ChangePassword() {
  const { changePassword } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
      setFailure(null);
      say(strings.passwordChanged);
    } catch (error) {
      setFailure(
        explain(error, {
          401: strings.errorWrongPassword,
          422: strings.errorWeakPassword(MIN_PASSWORD_LENGTH),
        }),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Section heading={strings.changePasswordHeading}>
      {notice}
      <form className="account-fields" onSubmit={submit} noValidate>
        <PasswordField
          label={strings.currentPasswordLabel}
          autoComplete="current-password"
          name="current-password"
          value={current}
          onChange={setCurrent}
        />
        <PasswordField
          label={strings.newPasswordLabel}
          hint={strings.passwordHint(MIN_PASSWORD_LENGTH)}
          autoComplete="new-password"
          name="new-password"
          value={next}
          onChange={setNext}
        />
        <button className="btn btn-primary" type="submit" aria-busy={busy}>
          {strings.changePasswordAction}
        </button>
      </form>
    </Section>
  );
}

function NewRecoveryCode({
  missing,
  onMade,
}: {
  missing: boolean;
  onMade: (code: string) => void;
}) {
  const { newRecoveryCode } = useReader();
  const { setFailure, notice } = useFailure();
  const [current, setCurrent] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      onMade(await newRecoveryCode(current));
    } catch (error) {
      setFailure(explain(error, { 401: strings.errorWrongPassword }));
      setBusy(false);
    }
  }

  return (
    <Section heading={strings.recoveryHeading}>
      {missing ? (
        <p className="notice notice-warn">{strings.recoveryMissing}</p>
      ) : (
        <p>{strings.recoveryReplaceIntro}</p>
      )}
      {notice}
      <form className="account-fields" onSubmit={submit} noValidate>
        <PasswordField
          label={strings.currentPasswordLabel}
          autoComplete="current-password"
          name="current-password"
          value={current}
          onChange={setCurrent}
        />
        <button className="btn" type="submit" aria-busy={busy}>
          {strings.newRecoveryAction}
        </button>
      </form>
    </Section>
  );
}

function SignOutEverywhere() {
  const { signOutEverywhere } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();

  return (
    <Section heading={strings.everywhereHeading}>
      <p>{strings.everywhereIntro}</p>
      {notice}
      <div className="notice-actions">
        <button
          className="btn"
          type="button"
          onClick={() => {
            signOutEverywhere().then(
              () => say(strings.signedOutEverywhere),
              (error) => setFailure(explain(error, {})),
            );
          }}
        >
          {strings.everywhereAction}
        </button>
      </div>
    </Section>
  );
}

function DeleteAccount() {
  const { deleteAccount } = useReader();
  const { say } = useAnnouncer();
  const { setFailure, notice } = useFailure();
  const [current, setCurrent] = useState("");
  const [confirming, setConfirming] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  async function erase() {
    setConfirming(false);
    try {
      await deleteAccount(current);
      say(strings.accountDeleted);
    } catch (error) {
      setFailure(explain(error, { 401: strings.errorWrongPassword }));
    }
  }

  return (
    <Section heading={strings.deleteAccountHeading}>
      <p>{strings.deleteAccountIntro}</p>
      {notice}
      <form
        className="account-fields"
        onSubmit={(event) => {
          event.preventDefault();
          setConfirming(true);
        }}
        noValidate
      >
        <PasswordField
          label={strings.currentPasswordLabel}
          autoComplete="current-password"
          name="delete-current-password"
          value={current}
          onChange={setCurrent}
        />
        <button ref={trigger} className="btn btn-danger" type="submit">
          {strings.deleteAccountAction}
        </button>
      </form>
      <ConfirmDialog
        open={confirming}
        title={strings.deleteAccountConfirmTitle}
        body={strings.deleteAccountConfirmBody}
        cancelLabel={strings.deleteConfirmCancel}
        confirmLabel={strings.deleteAccountAction}
        onCancel={() => setConfirming(false)}
        onConfirm={() => void erase()}
        returnFocusRef={trigger}
      />
    </Section>
  );
}
