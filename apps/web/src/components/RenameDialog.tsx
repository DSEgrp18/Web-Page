"use client";

import { useEffect, useId, useRef, useState } from "react";

import { strings } from "@/lib/strings";

/**
 * Giving a book the reader's own name.
 *
 * Modal, because it is one small decision with an obvious end. The field is
 * pre-filled with the current name and selected, so the common case — replacing
 * it — is one keystroke, and editing instead is still possible without deleting
 * first.
 *
 * Blank is allowed and means "no name of my own": the API clears the title and
 * the filename comes back. That is the only way to undo a rename, so the field
 * is deliberately not `required`.
 *
 * **Mounted only while it is open**, and keyed by book by the caller. That is
 * what makes `useState(current)` correct: there is no stale value to sync,
 * because opening it for a different book is a different component instance.
 * The alternative — keeping it mounted and copying the prop into state in an
 * effect — is a render with the wrong name in the field, every time.
 */
export function RenameDialog({
  current,
  onCancel,
  onSave,
  returnFocusTo,
}: {
  current: string;
  onCancel: () => void;
  onSave: (title: string) => void;
  returnFocusTo: React.RefObject<HTMLElement | null>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState(current);
  const fieldId = useId();
  const helpId = useId();

  useEffect(() => {
    dialog.current?.showModal();
    // After showModal, or moving focus into the dialog discards the selection.
    const timer = window.setTimeout(() => input.current?.select(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const close = () => {
    onCancel();
    returnFocusTo.current?.focus();
  };

  return (
    /* The backdrop click below is a pointer affordance on an element that is
       already a dialog. jsx-a11y does not know <dialog> is interactive, and a
       key handler here would be unreachable: Escape is handled by onCancel. */
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={dialog}
      className="dialog"
      aria-labelledby={`${fieldId}-heading`}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target === dialog.current) close();
      }}
    >
      <form
        method="dialog"
        className="dialog-body"
        onSubmit={(event) => {
          event.preventDefault();
          onSave(value);
          returnFocusTo.current?.focus();
        }}
      >
        <h2 id={`${fieldId}-heading`}>{strings.renameHeading}</h2>
        <div className="field">
          <label htmlFor={fieldId}>{strings.renameLabel}</label>
          <input
            ref={input}
            id={fieldId}
            type="text"
            value={value}
            maxLength={200}
            aria-describedby={helpId}
            onChange={(event) => setValue(event.target.value)}
          />
          <p className="hint" id={helpId}>
            {strings.renameHelp}
          </p>
        </div>
        <div className="dialog-actions">
          <button className="btn btn-primary" type="submit">
            {strings.renameSave}
          </button>
          <button className="btn" type="button" onClick={close}>
            {strings.deleteConfirmCancel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
