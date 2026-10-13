import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Settings } from "../src/components/Settings";
import { ReaderApi } from "../src/lib/client";
import { preferencesSnapshot, resetPreferences } from "../src/lib/preferences";
import { si as strings } from "../src/lib/strings";
import { FAKE_CSRF, FakeServer } from "./fakeApi";
import { renderApp } from "./render";

/** The server's readiness, as Settings asks for it, listing these voices. */
function serverWithVoices(voices: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ alive: true, voices })),
  );
}

async function openSettings() {
  renderApp(<Settings />, new FakeServer());
  await userEvent.click(screen.getByRole("button", { name: strings.settingsToggle }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("choosing the voice", () => {
  it("asks for audio in the chosen voice", async () => {
    const urls: string[] = [];
    const fetchImpl = vi.fn(async (url: string) => {
      urls.push(url);
      return new Response(new Uint8Array([1]), { status: 200 });
    }) as unknown as typeof fetch;
    const api = new ReaderApi(FAKE_CSRF, { baseUrl: "http://api.test", fetchImpl });

    await api.getAudio("doc-1", "0000-s0", undefined, "si-male");
    await api.getAudio("doc-1", "0000-s0");

    expect(urls[0]).toMatch(/\/audio\?voice=si-male$/);
    // No voice named is the server's default, and the address it always was.
    expect(urls[1]).toMatch(/\/audio$/);
  });

  it("offers the male voice once the server has it", async () => {
    serverWithVoices(["si-female", "si-male"]);
    await openSettings();

    const male = screen.getByRole("radio", { name: strings.voiceMale });
    await waitFor(() => expect((male as HTMLInputElement).disabled).toBe(false));
    await userEvent.click(male);

    expect(preferencesSnapshot().voice).toBe("si-male");
  });

  it("disables the male voice, and says why, while the server lacks it", async () => {
    serverWithVoices(["si-female"]);
    await openSettings();

    await waitFor(() =>
      expect(
        (screen.getByRole("radio", { name: strings.voiceMale }) as HTMLInputElement).disabled,
      ).toBe(true),
    );
    expect(
      (screen.getByRole("radio", { name: strings.voiceFemale }) as HTMLInputElement).checked,
    ).toBe(true);
    expect(screen.getByText(strings.voiceMaleUnavailable)).toBeTruthy();
  });

  it("forgets a stored voice it does not know", () => {
    window.localStorage.setItem("swara.preferences", JSON.stringify({ voice: "en-robot" }));
    resetPreferences();
    expect(preferencesSnapshot().voice).toBe("si-female");
  });
});
