import { render } from "@testing-library/react";
import type { ReactElement } from "react";

import { AnnouncerProvider } from "../src/components/Announcer";
import { ReaderProvider } from "../src/components/ReaderProvider";
import type { FakeServer } from "./fakeApi";
import { OWNER } from "./fakeApi";

/**
 * Render a screen inside the same providers the real app uses, talking to a
 * fake server through the real client.
 *
 * `clientOptions` is built once per call and never re-created: it is a
 * dependency of the memo that builds the API client, and a fresh object on
 * every render would rebuild the client, which would re-run every fetch effect,
 * forever.
 */
export function renderApp(ui: ReactElement, server: FakeServer, owner: string = OWNER) {
  const clientOptions = { baseUrl: "http://api.test", fetchImpl: server.fetch };
  return render(
    <AnnouncerProvider>
      <ReaderProvider ownerOverride={owner} clientOptions={clientOptions}>
        {ui}
      </ReaderProvider>
    </AnnouncerProvider>,
  );
}

/** What the interface has said politely — progress, confirmation. */
export function politeText(): string {
  return document.querySelector('[role="status"]')?.textContent ?? "";
}

/** What the interface has interrupted with — errors only. */
export function assertiveText(): string {
  return document.querySelector('[role="alert"]')?.textContent ?? "";
}

/**
 * The error shown on the page, as distinct from the one announced.
 *
 * They are separate on purpose and the same message appears in both, so a test
 * asking "is this on screen" has to say which one it means.
 */
export function noticeText(): string {
  return document.querySelector(".notice.error")?.textContent ?? "";
}
