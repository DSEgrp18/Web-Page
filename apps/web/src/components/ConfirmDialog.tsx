"use client";

import { useEffect, useId, useRef, type ReactNode, type RefObject } from "react";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  body: ReactNode;
  cancelLabel: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: () => void;
  /** The control that opened the dialog — focus returns here on close. */
  returnFocusRef: RefObject<HTMLElement | null>;
};

/**
 * Destructive confirmation built on the native `<dialog>`.
 *
 * Native `showModal()` gives the focus trap, backdrop and Escape for free.
 * Focus opens on **cancel**, not the destructive action, so Enter-out-of-habit
 * cannot delete a book.
 */
export function ConfirmDialog({
  open,
  title,
  body,
  cancelLabel,
  confirmLabel,
  onCancel,
  onConfirm,
  returnFocusRef,
}: ConfirmDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const bodyId = useId();
  /** Track whether *this* open cycle closed, so we restore focus once. */
  const wasOpenRef = useRef(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      wasOpenRef.current = true;
      if (!dialog.open) dialog.showModal();
      // Defer so the dialog is in the top layer before moving focus.
      queueMicrotask(() => cancelRef.current?.focus());
      return;
    }

    if (dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const onClose = () => {
      if (!wasOpenRef.current) return;
      wasOpenRef.current = false;
      returnFocusRef.current?.focus();
    };

    dialog.addEventListener("close", onClose);
    return () => dialog.removeEventListener("close", onClose);
  }, [returnFocusRef]);

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <h2 id={titleId}>{title}</h2>
      <p id={bodyId}>{body}</p>
      <div className="row">
        <button ref={cancelRef} type="button" onClick={onCancel}>
          {cancelLabel}
        </button>
        <button type="button" className="danger" onClick={onConfirm}>
          {confirmLabel}
        </button>
      </div>
    </dialog>
  );
}
