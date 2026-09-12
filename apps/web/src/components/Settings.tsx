"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";

import { usePreferences } from "@/components/PreferencesProvider";
import { strings, themeName } from "@/lib/strings";
import { TEXT_SCALES, type Theme } from "@/lib/preferences";

/**
 * Reading settings, in the masthead, on every screen.
 *
 * A disclosure rather than a dialog: nothing here is modal, and a reader
 * changing the text size wants to watch the text change behind the panel, not
 * be locked out of it until they dismiss something.
 *
 * Three groups, each a real fieldset with a real legend, because that is what
 * makes a screen reader say "theme, radio button, 1 of 3" instead of reading
 * three unrelated buttons. Radios for the things that are one-of-many, switches
 * for the things that are on or off.
 *
 * Closing returns focus to the button that opened it. Escape closes. A click
 * outside closes — but a click outside is a mouse gesture, so it is a
 * convenience on top of Escape, never the only way out.
 */
export function Settings() {
  const { preferences, set } = usePreferences();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const toggleRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    toggleRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    const onPointer = (event: PointerEvent) => {
      const target = event.target as Node;
      if (panelRef.current?.contains(target) || toggleRef.current?.contains(target)) return;
      // Not `close()`: a click elsewhere should not yank focus back to the
      // toggle, because the reader is already on their way somewhere else.
      setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open, close]);

  return (
    <div className="settings">
      <button
        ref={toggleRef}
        type="button"
        className="btn btn-quiet btn-icon"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((wasOpen) => !wasOpen)}
      >
        <GearIcon />
        <span className="visually-hidden">{strings.settingsToggle}</span>
      </button>

      <div
        id={panelId}
        ref={panelRef}
        className="settings-panel card"
        hidden={!open}
        role="group"
        aria-label={strings.settingsHeading}
      >
        <fieldset className="settings-group">
          <legend>{strings.settingsTheme}</legend>
          <div className="segmented">
            {(["system", "light", "dark"] as Theme[]).map((theme) => (
              <label key={theme} className="segment">
                <input
                  type="radio"
                  name="swara-theme"
                  value={theme}
                  checked={preferences.theme === theme}
                  onChange={() => set("theme", theme)}
                />
                <span>{themeName(theme)}</span>
              </label>
            ))}
          </div>
        </fieldset>

        <fieldset className="settings-group">
          <legend>{strings.settingsTextSize}</legend>
          <div className="segmented">
            {TEXT_SCALES.map((scale) => (
              <label key={scale} className="segment">
                <input
                  type="radio"
                  name="swara-scale"
                  value={scale}
                  checked={preferences.textScale === scale}
                  onChange={() => set("textScale", scale)}
                />
                {/* The number is the label a sighted reader scans; the
                    percentage is what a screen reader should say. */}
                <span aria-hidden="true" style={{ fontSize: `${0.8 + (scale - 0.9) * 0.7}rem` }}>
                   අ
                </span>
                <span className="visually-hidden">{strings.textSizePercent(scale)}</span>
              </label>
            ))}
          </div>
          <p className="hint">{strings.settingsTextSizeHelp}</p>
        </fieldset>

        <fieldset className="settings-group">
          <legend>{strings.settingsReading}</legend>
          <Switch
            label={strings.settingFollowSentence}
            checked={preferences.followSentence}
            onChange={(next) => set("followSentence", next)}
          />
          <Switch
            label={strings.settingPageTurnSound}
            hint={strings.settingPageTurnSoundHelp}
            checked={preferences.pageTurnSound}
            onChange={(next) => set("pageTurnSound", next)}
          />
        </fieldset>

        <button type="button" className="btn btn-sm" onClick={close}>
          {strings.closePanel}
        </button>
      </div>
    </div>
  );
}

/**
 * A real checkbox with `role="switch"`.
 *
 * Not a styled `<div onClick>`: the checkbox is what gives keyboard operation,
 * the checked state, and the label association for free. `role="switch"` only
 * changes how it is announced — "on"/"off" rather than "checked" — which is
 * what these actually are.
 */
function Switch({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  const hintId = useId();
  return (
    <label className="switch">
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        aria-describedby={hint ? hintId : undefined}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span className="switch-track" aria-hidden="true">
        <span className="switch-thumb" />
      </span>
      <span className="switch-label">
        {label}
        {hint ? (
          <span className="hint" id={hintId}>
            {hint}
          </span>
        ) : null}
      </span>
    </label>
  );
}

function GearIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
      <path
        d="M19.4 13a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5v.2a2 2 0 1 1-4 0v-.1a1.6 1.6 0 0 0-1-1.5 1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.6 1.6 0 0 0 1.5-1 1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1h.2a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1Z"
        stroke="currentColor"
        strokeWidth="1.7"
      />
    </svg>
  );
}
