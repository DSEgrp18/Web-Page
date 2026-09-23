"use client";

import { useCallback, useEffect, useId, useRef, useState, type DragEvent } from "react";

import { useAnnouncer } from "@/components/Announcer";
import { useReader } from "@/components/ReaderProvider";
import { ApiError } from "@/lib/client";
import { messageFor, strings } from "@/lib/strings";
import type { DocumentDetail } from "@/lib/types";

/** What the API refuses above. Checked here too, so the reader hears it sooner. */
const MAX_BYTES = 50 * 1024 * 1024;

/**
 * Adding a book.
 *
 * A real modal this time, unlike the settings disclosure: while this is open
 * there is exactly one thing to do, and the library behind it is not something
 * to interact with half-way through an upload.
 *
 * `<dialog showModal()>` does the work the platform is better at than we are —
 * focus trapping, inertness of the background, Escape, and the top layer. What
 * is added on top is the two things it does not do: returning focus to the
 * button that opened it (browsers vary), and refusing to close while an upload
 * is in flight, because a cancelled dialog does not cancel a request.
 *
 * ## Drag and drop is the convenience, not the mechanism
 *
 * The file input is real and focusable. Dropping is an alternative for people
 * with a pointer; it is never the only way in, and the dropzone is a `<label>`
 * for the input so clicking anywhere on it opens the picker.
 */
export function UploadDialog({
  open,
  onClose,
  onUploaded,
}: {
  open: boolean;
  onClose: () => void;
  onUploaded: (created: DocumentDetail) => void | Promise<void>;
}) {
  const { api } = useReader();
  const { say, alert } = useAnnouncer();
  const dialog = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const [files, setFiles] = useState<File[]>([]);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const fileId = useId();
  const titleId = useId();
  const helpId = useId();
  const problemId = useId();

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    if (open && !element.open) {
      element.showModal();
    } else if (!open && element.open) {
      element.close();
    }
  }, [open]);

  const close = useCallback(() => {
    // A dialog that closes mid-upload leaves a request running with nothing
    // watching it, and the reader with no idea whether the book arrived.
    if (busy) return;
    setFiles([]);
    setTitle("");
    setProblem(null);
    setDragging(false);
    onClose();
  }, [busy, onClose]);

  /** Validate here so the reader hears the reason before a round trip. */
  const accept = useCallback(
    (chosen: FileList | File[] | null | undefined) => {
      const selected = Array.from(chosen ?? []);
      if (!selected.length) return;
      const allowed = selected.every(
        (item) => /\.(pdf|docx|png|jpe?g)$/i.test(item.name) || !/\.[^./\\]+$/.test(item.name),
      );
      if (!allowed) {
        setProblem(strings.uploadUnsupported);
        alert(strings.uploadUnsupported);
        return;
      }
      if (selected.some((item) => item.size > MAX_BYTES)) {
        setProblem(strings.uploadTooBig);
        alert(strings.uploadTooBig);
        return;
      }
      setProblem(null);
      setFiles(selected);
      say(
        selected.length === 1
          ? strings.uploadSelectedFile(selected[0]?.name ?? "")
          : strings.uploadSelectedCount(selected.length),
      );
    },
    [alert, say],
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLLabelElement>) => {
      event.preventDefault();
      setDragging(false);
      accept(event.dataTransfer.files);
    },
    [accept],
  );

  const submit = useCallback(async () => {
    if (!files.length) {
      setProblem(strings.uploadNoFile);
      alert(strings.uploadNoFile);
      input.current?.focus();
      return;
    }
    setBusy(true);
    setProblem(null);
    say(strings.uploadInProgress);
    const remaining = [...files];
    try {
      while (remaining.length) {
        const file = remaining[0];
        if (!file) break;
        let created = await api.upload(file);
        const chosen = title.trim();
        if (chosen && files.length === 1) {
          try {
            created = await api.renameDocument(created.document_id, chosen);
          } catch {
            // The document is in. Its optional display name can be set again.
          }
        }
        remaining.shift();
        await onUploaded(created);
      }
      setFiles([]);
      setTitle("");
      setBusy(false);
      onClose();
      say(strings.preparing);
    } catch (cause) {
      setFiles(remaining);
      const message = cause instanceof ApiError ? messageFor(cause.kind) : strings.uploadFailed;
      setProblem(message);
      alert(message);
      setBusy(false);
    }
  }, [alert, api, files, onClose, onUploaded, say, title]);

  return (
    /* The backdrop click below is a pointer affordance on an element that is
       already a dialog. jsx-a11y does not know <dialog> is interactive, and a
       key handler here would be unreachable: Escape is handled by onCancel. */
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions
    <dialog
      ref={dialog}
      className="dialog upload-dialog"
      aria-labelledby={`${fileId}-heading`}
      onCancel={(event) => {
        // Escape. Prevented while busy, for the same reason as `close`.
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        // The backdrop is the dialog element itself; a click on a child is not
        // on the backdrop. Convenience only — Escape is the real way out.
        if (event.target === dialog.current) close();
      }}
    >
      <form
        method="dialog"
        className="dialog-body"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <h2 id={`${fileId}-heading`}>{strings.uploadDialogHeading}</h2>
        <p className="hint">{strings.uploadHelp}</p>

        {problem ? (
          <p className="notice notice-bad" id={problemId} role="alert">
            {problem}
          </p>
        ) : null}

        <label
          className="dropzone"
          htmlFor={fileId}
          data-dragging={dragging}
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <UploadIcon />
          <span className="dropzone-title">{strings.uploadDrop}</span>
          <span className="hint">{strings.uploadOr}</span>
          <span className="btn btn-sm dropzone-button" aria-hidden="true">
            {strings.uploadChoose}
          </span>
          <span className="hint" id={helpId}>
            {strings.uploadFormats}
          </span>
        </label>
        <input
          ref={input}
          id={fileId}
          className="visually-hidden"
          type="file"
          accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx,image/png,.png,image/jpeg,.jpg,.jpeg"
          multiple
          // The label element exists so that clicking the dropzone opens the
          // picker. As an accessible *name* its whole text is far too long, so
          // the name is set here and the rest becomes the description.
          aria-label={strings.uploadChoose}
          aria-describedby={problem ? `${helpId} ${problemId}` : helpId}
          disabled={busy}
          onChange={(event) => accept(event.target.files)}
        />

        {files.length ? (
          <div className="chosen-file">
            <ul className="upload-file-list">
              {files.map((file) => (
                <li key={`${file.name}-${file.size}`}>
                  <span className="chosen-file-name">{file.name}</span>{" "}
                  <span className="hint latin">{strings.fileSize(file.size)}</span>
                </li>
              ))}
            </ul>
            <button
              type="button"
              className="btn btn-quiet btn-sm"
              disabled={busy}
              onClick={() => {
                setFiles([]);
                if (input.current) input.current.value = "";
                input.current?.focus();
              }}
            >
              {strings.removeFiles}
            </button>
          </div>
        ) : null}

        <div className="field">
          <label htmlFor={titleId}>{strings.uploadTitleLabel}</label>
          <input
            id={titleId}
            type="text"
            value={title}
            maxLength={200}
            disabled={busy}
            aria-describedby={`${titleId}-help`}
            onChange={(event) => setTitle(event.target.value)}
          />
          <p className="hint" id={`${titleId}-help`}>
            {files.length > 1 ? strings.uploadTitleSingleOnly : strings.uploadTitleHelp}
          </p>
        </div>

        <div className="dialog-actions">
          <button className="btn btn-primary" type="submit" disabled={busy || !files.length}>
            {busy ? strings.uploadInProgress : strings.uploadSubmit}
          </button>
          <button className="btn" type="button" onClick={close} disabled={busy}>
            {strings.deleteConfirmCancel}
          </button>
        </div>
      </form>
    </dialog>
  );
}

function UploadIcon() {
  return (
    <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}
