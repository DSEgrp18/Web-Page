import { act, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocaleProvider } from "../src/components/LocaleProvider";
import {
  FIRST_LOAD_MIN_MS,
  LoadingProvider,
  MAX_COVER_MS,
  SHOW_AFTER_MS,
  useBusy,
} from "../src/components/LoadingScreen";
import { si as strings } from "../src/lib/strings";

/**
 * The loading screen's timing. Fake timers, `performance` included, so "the
 * page began loading" is time zero and every wait is exact.
 */

let setLoading: (loading: boolean) => void = () => {};

function Page({ initiallyLoading = false }: { initiallyLoading?: boolean }) {
  const [loading, set] = useState(initiallyLoading);
  setLoading = (value) => act(() => set(value));
  useBusy(loading);
  return <button type="button">{strings.libraryHeading}</button>;
}

function renderScreen(initiallyLoading = false) {
  return render(
    <LocaleProvider locale="si">
      <LoadingProvider>
        <Page initiallyLoading={initiallyLoading} />
      </LoadingProvider>
    </LocaleProvider>,
  );
}

/** The screen's status line, or null once it has gone. */
const status = () => screen.queryByRole("status");

/**
 * Let time pass in small steps, as it does: each step lets React run the
 * effects the last one caused, such as the fade-out a lifted screen schedules.
 */
function advance(ms: number) {
  for (let passed = 0; passed < ms; passed += 20) {
    act(() => {
      vi.advanceTimersByTime(Math.min(20, ms - passed));
    });
  }
}

beforeEach(() => {
  vi.useFakeTimers({
    toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "performance"],
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe("the loading screen", () => {
  it("holds five seconds after a refresh, then lifts by itself", () => {
    expect(FIRST_LOAD_MIN_MS).toBe(5000);
    renderScreen();
    expect(status()?.textContent).toBe(strings.loadingSession);

    advance(4900);
    expect(status()).not.toBeNull();

    advance(100); // the minimum is met: it fades out
    advance(400); // and leaves the document
    expect(status()).toBeNull();
  });

  it("keeps the page out of reach while it is up", () => {
    const { container } = renderScreen();
    // The page is a sibling of the screen, and inert until the screen goes.
    expect(container.firstElementChild?.hasAttribute("inert")).toBe(true);

    advance(5400);
    expect(container.firstElementChild?.hasAttribute("inert")).toBe(false);
    expect(screen.getByRole("button", { name: strings.libraryHeading })).toBeTruthy();
  });

  it("after the minimum, waits for a page that is still loading", () => {
    renderScreen(true);
    advance(8000);
    expect(status()).not.toBeNull();

    setLoading(false);
    advance(400);
    expect(status()).toBeNull();
  });

  it("never flashes for a quick page load, and covers a slow one", () => {
    renderScreen();
    advance(5400);
    expect(status()).toBeNull();

    // Quick: answered before SHOW_AFTER_MS.
    setLoading(true);
    advance(SHOW_AFTER_MS - 100);
    setLoading(false);
    advance(1000);
    expect(status()).toBeNull();

    // Slow: past SHOW_AFTER_MS, and it shows the page-loading words.
    setLoading(true);
    advance(SHOW_AFTER_MS + 50);
    expect(status()?.textContent).toBe(strings.pageLoading);

    setLoading(false);
    advance(1000);
    expect(status()).toBeNull();
  });

  it("gives up rather than trap a reader behind a load that never ends", () => {
    renderScreen(true);
    advance(FIRST_LOAD_MIN_MS + MAX_COVER_MS + 400);
    expect(status()).toBeNull();
  });
});
