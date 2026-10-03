import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { Reader } from "../src/components/Reader";
import { AHEAD, IN_FLIGHT } from "../src/lib/usePlayer";
import { si as strings } from "../src/lib/strings";
import { FakeServer, readablePage, type FakeBook } from "./fakeApi";
import { renderApp } from "./render";
import { playCalls } from "./setup";

/**
 * The sentences ahead of the one playing are made while it plays.
 *
 * Generating a sentence takes about as long as hearing it, so the player asks
 * for the next few as soon as play is pressed, alongside the first, in reading
 * order and a few at a time, and stops asking when the reader pauses. These
 * tests hold every audio response open, so what is asked for, and when, can be
 * read exactly.
 */

const SENTENCES = ["එක.", "දෙක.", "තුන.", "හතර.", "පහ.", "හය.", "හත."];
const id = (index: number) => `0000-s${index}`;

/** Audio answers only when a test releases it. */
class HeldAudio extends FakeServer {
  readonly asked: string[] = [];
  private readonly held = new Map<string, () => void>();

  override get fetch(): typeof fetch {
    const real = super.fetch;
    return (async (input: RequestInfo | URL, init?: RequestInit) => {
      const match = /segments\/([^/]+)\/audio$/.exec(String(input));
      if (match) {
        const segment = match[1]!;
        this.asked.push(segment);
        await new Promise<void>((resolve) => this.held.set(segment, resolve));
      }
      return real(input, init);
    }) as typeof fetch;
  }

  inFlight(): number {
    return this.held.size;
  }

  release(...segments: string[]): void {
    for (const segment of segments) {
      const answer = this.held.get(segment);
      this.held.delete(segment);
      answer?.();
    }
  }
}

function openBook(): HeldAudio {
  const book: FakeBook = {
    document_id: "doc-1",
    filename: "පොත.pdf",
    version: "v1",
    pages: [readablePage(0, SENTENCES)],
  };
  const server = new HeldAudio({ books: [book] });
  renderApp(<Reader documentId="doc-1" />, server);
  return server;
}

/** Long enough for any request the player was going to make to have been made. */
const settle = () => new Promise((resolve) => setTimeout(resolve, 50));

describe("the sentences ahead", () => {
  it("are asked for with the first sentence, in order, a few at a time", async () => {
    const user = userEvent.setup();
    const server = openBook();

    await user.click(await screen.findByRole("button", { name: SENTENCES[0] }));

    // Not one after another: the first and the two after it, together.
    await waitFor(() => expect(server.asked).toEqual([id(0), id(1), id(2)]));
    expect(server.inFlight()).toBe(IN_FLIGHT);

    // The first arrives and plays; its slot goes to the next in reading order.
    server.release(id(0));
    await waitFor(() => expect(playCalls).toHaveLength(1));
    await waitFor(() => expect(server.asked).toEqual([id(0), id(1), id(2), id(3)]));
    expect(server.inFlight()).toBe(IN_FLIGHT);
  });

  it(`go no further than ${AHEAD} past the sentence playing`, async () => {
    const user = userEvent.setup();
    const server = openBook();

    await user.click(await screen.findByRole("button", { name: SENTENCES[0] }));
    await waitFor(() => expect(server.asked).toHaveLength(IN_FLIGHT));
    server.release(id(0));
    await waitFor(() => expect(playCalls).toHaveLength(1));

    for (let round = 0; round < 3; round += 1) {
      server.release(...server.asked);
      await settle();
    }

    // The first sentence is still playing: the window is the four after it.
    expect(server.asked).toEqual([id(0), id(1), id(2), id(3), id(4)]);
    expect(server.asked).not.toContain(id(5));
  });

  it("stop being asked for when the reader pauses", async () => {
    const user = userEvent.setup();
    const server = openBook();

    await user.click(await screen.findByRole("button", { name: SENTENCES[0] }));
    await waitFor(() => expect(server.asked).toHaveLength(IN_FLIGHT));
    server.release(id(0));
    await waitFor(() => expect(playCalls).toHaveLength(1));
    await waitFor(() => expect(server.asked).toHaveLength(IN_FLIGHT + 1));

    await user.click(screen.getByRole("button", { name: strings.pause }));
    const before = [...server.asked];
    server.release(...server.asked);
    await settle();

    // What was already being made finishes; nothing new is started.
    expect(server.asked).toEqual(before);
  });

  it("are not asked for before anyone presses play", async () => {
    const server = openBook();
    await screen.findByRole("button", { name: SENTENCES[0] });
    await settle();
    expect(server.asked).toEqual([]);
  });
});
