"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type InputHTMLAttributes,
  type ReactNode,
} from "react";

import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { SignedIn } from "@/lib/types";

/**
 * Signing in, making an account, and getting back into one.
 *
 * Built for a screen reader and a phone first:
 *
 * - Every field has a visible label and the `autocomplete` a password manager
 *   and the platform's autofill need, so nothing has to be typed that the
 *   device already knows (WCAG 2.2, 3.3.7 and 3.3.8). No CAPTCHA, anywhere.
 * - A password can be shown, because typing one blind, on a phone, with a
 *   screen reader speaking each character as a star, is how mistakes happen.
 * - A refusal is one sentence saying what to do, placed above the form and
 *   given focus, so it is heard at once and read again with the next swipe.
 *   It is not also announced: focus already says it, and hearing it twice
 *   teaches a reader that two messages might be one.
 */

/** The password rule the API enforces, so the hint and the refusal agree. */
export const MIN_PASSWORD_LENGTH = 10;

function useFailure() {
  const [failure, setFailure] = useState<string | null>(null);
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (failure) ref.current?.focus();
  }, [failure]);
  const notice = failure ? (
    <p ref={ref} tabIndex={-1} className="notice notice-bad">
      {failure}
    </p>
  ) : null;
  return { failure, setFailure, notice };
}

/** What to say for a failed account request, given what each route refuses with. */
function explain(error: unknown, when: Partial<Record<number, string>>): string {
  if (error instanceof ApiError) {
    const specific = when[error.status];
    if (specific) return specific;
    return messageFor(error.kind);
  }
  return strings.errorServer;
}

function Field({
  label,
  hint,
  ...input
}: {
  label: string;
  hint?: string;
} & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <input id={id} aria-describedby={hint ? hintId : undefined} {...input} />
      {hint ? (
        <p className="hint" id={hintId}>
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function PasswordField({
  label,
  hint,
  autoComplete,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  autoComplete: "current-password" | "new-password";
  value: string;
  onChange: (value: string) => void;
}) {
  const [shown, setShown] = useState(false);
  const toggleId = useId();
  return (
    <>
      <Field
        label={label}
        hint={hint}
        name="password"
        type={shown ? "text" : "password"}
        autoComplete={autoComplete}
        required
        minLength={autoComplete === "new-password" ? MIN_PASSWORD_LENGTH : undefined}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <div className="check-row">
        <input
          id={toggleId}
          type="checkbox"
          checked={shown}
          onChange={(event) => setShown(event.target.checked)}
        />
        <label htmlFor={toggleId}>{strings.showPassword}</label>
      </div>
    </>
  );
}

function AccountScreen({ heading, children }: { heading: string; children: ReactNode }) {
  const headingId = useId();
  return (
    <div className="account-screen">
      <section className="account-form card" aria-labelledby={headingId}>
        <h1 id={headingId}>{heading}</h1>
        {children}
      </section>
    </div>
  );
}

/** Where to go after signing in: back where the reader was sent from, or home. */
export function nextPath(search: string): string {
  const asked = new URLSearchParams(search).get("next");
  // Only a path on this site; never somewhere a crafted link names.
  return asked && asked.startsWith("/") && !asked.startsWith("//") && !asked.includes("\\")
    ? asked
    : "/";
}

export function SignInForm() {
  const { signIn } = useReader();
  const { say } = useAnnouncer();
  const router = useRouter();
  const { setFailure, notice } = useFailure();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await signIn(email, password);
      say(strings.signedIn);
      router.replace(nextPath(window.location.search));
    } catch (error) {
      setFailure(explain(error, { 401: strings.errorSignIn }));
      setBusy(false);
    }
  }

  return (
    <AccountScreen heading={strings.signInHeading}>
      {notice}
      <form className="account-fields" onSubmit={submit} noValidate>
        <Field
          label={strings.emailLabel}
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <PasswordField
          label={strings.passwordLabel}
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
        />
        <button className="btn btn-primary" type="submit" aria-busy={busy}>
          {strings.signInAction}
        </button>
      </form>
      <p>
        <Link href="/recover">{strings.forgotPassword}</Link>
      </p>
      <p>
        {strings.noAccountYet} <Link href="/register">{strings.registerHeading}</Link>
      </p>
    </AccountScreen>
  );
}

export function RegisterForm() {
  const { register } = useReader();
  const { setFailure, notice } = useFailure();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<SignedIn | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      setMade(await register(email, password, name));
    } catch (error) {
      setFailure(
        explain(error, {
          409: strings.errorEmailTaken,
          422: strings.errorWeakPassword(MIN_PASSWORD_LENGTH),
        }),
      );
      setBusy(false);
    }
  }

  if (made?.recovery_code) {
    return <RecoveryCode email={made.account.email} code={made.recovery_code} />;
  }

  return (
    <AccountScreen heading={strings.registerHeading}>
      {notice}
      <form className="account-fields" onSubmit={submit} noValidate>
        <Field
          label={strings.displayNameLabel}
          hint={strings.displayNameHint}
          name="name"
          autoComplete="name"
          required
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Field
          label={strings.emailLabel}
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <PasswordField
          label={strings.passwordLabel}
          hint={strings.passwordHint(MIN_PASSWORD_LENGTH)}
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
        />
        <button className="btn btn-primary" type="submit" aria-busy={busy}>
          {strings.registerAction}
        </button>
      </form>
      <p>
        {strings.haveAccount} <Link href="/sign-in">{strings.signInHeading}</Link>
      </p>
    </AccountScreen>
  );
}

export function RecoverForm() {
  const { recover } = useReader();
  const { setFailure, notice } = useFailure();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [recovered, setRecovered] = useState<SignedIn | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      setRecovered(await recover(email, code, password));
    } catch (error) {
      setFailure(
        explain(error, {
          401: strings.errorRecover,
          422: strings.errorWeakPassword(MIN_PASSWORD_LENGTH),
        }),
      );
      setBusy(false);
    }
  }

  if (recovered?.recovery_code) {
    return <RecoveryCode email={recovered.account.email} code={recovered.recovery_code} />;
  }

  return (
    <AccountScreen heading={strings.recoverHeading}>
      <p>{strings.recoverIntro}</p>
      {notice}
      <form className="account-fields" onSubmit={submit} noValidate>
        <Field
          label={strings.emailLabel}
          name="email"
          type="email"
          autoComplete="email"
          inputMode="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <Field
          label={strings.recoveryCodeLabel}
          hint={strings.recoveryCodeHint}
          name="recovery-code"
          autoComplete="one-time-code"
          autoCapitalize="characters"
          spellCheck={false}
          required
          value={code}
          onChange={(event) => setCode(event.target.value)}
        />
        <PasswordField
          label={strings.newPasswordLabel}
          hint={strings.passwordHint(MIN_PASSWORD_LENGTH)}
          autoComplete="new-password"
          value={password}
          onChange={setPassword}
        />
        <button className="btn btn-primary" type="submit" aria-busy={busy}>
          {strings.recoverAction}
        </button>
      </form>
      <p>
        <Link href="/sign-in">{strings.signInHeading}</Link>
      </p>
    </AccountScreen>
  );
}

/**
 * The recovery code, shown once, and kept on screen until the reader says it
 * is safe. Moving on is a deliberate step: a code that scrolls away with the
 * next screen is a code nobody saved.
 */
export function RecoveryCode({ email, code }: { email: string; code: string }) {
  const { say } = useAnnouncer();
  const router = useRouter();
  const [saved, setSaved] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const confirmId = useId();

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(code);
      say(strings.codeCopied);
    } catch {
      // No clipboard permission: the code is on screen and in the download.
    }
  }

  function download() {
    const blob = new Blob([strings.recoveryFileText(email, code)], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = strings.recoveryFileName;
    link.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="account-screen">
      <section className="account-form card" aria-labelledby={`${confirmId}-heading`}>
        <h1 id={`${confirmId}-heading`} ref={headingRef} tabIndex={-1}>
          {strings.recoveryCodeHeading}
        </h1>
        <p>{strings.recoveryCodeIntro}</p>
        {/* Spelled out for a screen reader, one group at a time. */}
        <p className="recovery-code latin" translate="no">
          {code}
        </p>
        <div className="notice-actions">
          <button className="btn" type="button" onClick={() => void copy()}>
            {strings.copyCode}
          </button>
          <button className="btn" type="button" onClick={download}>
            {strings.downloadCode}
          </button>
        </div>
        <div className="check-row">
          <input
            id={confirmId}
            type="checkbox"
            checked={saved}
            onChange={(event) => setSaved(event.target.checked)}
          />
          <label htmlFor={confirmId}>{strings.savedCodeConfirm}</label>
        </div>
        <button
          className="btn btn-primary"
          type="button"
          disabled={!saved}
          onClick={() => router.replace("/")}
        >
          {strings.continueToLibrary}
        </button>
      </section>
    </div>
  );
}
