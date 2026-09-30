/**
 * The interface in two languages: Sinhala, the default, and English.
 *
 * What these guard is that the two dictionaries cannot drift apart unnoticed,
 * that the choice of language is the reader's and survives to the server, and
 * that the book itself is never read with the interface's voice: its words are
 * Sinhala in either interface, and are marked so.
 */

import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { AppFrame } from "../src/components/AppFrame";
import { Bookmarks } from "../src/components/Bookmarks";
import { Library } from "../src/components/Library";
import { Practice } from "../src/components/Practice";
import { Reader } from "../src/components/Reader";
import { contentFor } from "../src/lib/content";
import { LOCALE_COOKIE, parseLocale, scriptLang, stringsFor } from "../src/lib/i18n";
import { si } from "../src/lib/strings";
import { en } from "../src/lib/strings.en";
import { FakeServer, readablePage } from "./fakeApi";
import { renderApp } from "./render";
import { navigations } from "./setup";

const SINHALA = /[඀-෿]/;

describe("the two dictionaries", () => {
  it("have the same keys", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(si).sort());
  });

  it("have the same kind of thing under every key, and functions take the same arguments", () => {
    for (const key of Object.keys(si) as (keyof typeof si)[]) {
      const sinhala = si[key] as unknown;
      const english = en[key] as unknown;
      expect(typeof english, key).toBe(typeof sinhala);
      if (typeof sinhala === "function") {
        expect((english as (...args: never[]) => unknown).length, key).toBe(sinhala.length);
      }
      if (sinhala !== null && typeof sinhala === "object") {
        expect(Object.keys(english as object).sort(), key).toEqual(Object.keys(sinhala).sort());
      }
    }
  });

  it("count in English as English does", () => {
    expect(en.pageCount(1)).toBe("1 page");
    expect(en.pageCount(2)).toBe("2 pages");
    expect(en.sentenceCount(1)).toBe("1 sentence");
    expect(en.offlineMissing(1)).toBe("1 sentence has no audio.");
  });

  it("leave nothing empty", () => {
    for (const [key, value] of Object.entries(en)) {
      if (typeof value === "string") expect(value.trim(), key).not.toBe("");
    }
  });

  it("have no Sinhala left in the English", () => {
    const found: string[] = [];
    const visit = (key: string, value: unknown): void => {
      if (typeof value === "string" && SINHALA.test(value)) found.push(key);
      else if (typeof value === "function") {
        // Called as the interface calls it; some take words, some numbers.
        const call = (arg: unknown) => {
          try {
            return (value as (...a: unknown[]) => unknown)(...Array(value.length).fill(arg));
          } catch {
            return undefined;
          }
        };
        const result = call("x") ?? call(1);
        expect(result, `${key} could not be called`).toBeDefined();
        visit(key, result);
      } else if (value !== null && typeof value === "object") {
        for (const [inner, v] of Object.entries(value)) visit(`${key}.${inner}`, v);
      }
    };
    for (const [key, value] of Object.entries(en)) visit(key, value);
    expect(found).toEqual([]);
  });
});

describe("the public pages", () => {
  it("exist in both languages", () => {
    expect(Object.keys(contentFor("en")).sort()).toEqual(Object.keys(contentFor("si")).sort());
  });

  it("mark the English privacy notice, terms and accessibility statement as drafts for review", () => {
    const english = contentFor("en");
    expect(english.privacy.draft).toBe(true);
    expect(english.terms.draft).toBe(true);
    expect(english.accessibility.draft).toBe(true);
    // The Sinhala is the text of record, and is not a draft of anything.
    const sinhala = contentFor("si");
    expect(sinhala.privacy.draft).toBeFalsy();
    expect(sinhala.terms.draft).toBeFalsy();
    expect(sinhala.accessibility.draft).toBeFalsy();
  });
});

describe("choosing a language", () => {
  it("is Sinhala unless English was chosen", () => {
    expect(parseLocale(undefined)).toBe("si");
    expect(parseLocale("")).toBe("si");
    expect(parseLocale("fr")).toBe("si");
    expect(parseLocale("si")).toBe("si");
    expect(parseLocale("en")).toBe("en");
  });

  it("goes through components, never straight to a dictionary", () => {
    // A component that imports `si` or `en` would show that language whatever
    // the reader chose. Only the language modules may.
    const offenders: string[] = [];
    const walk = (dir: string): void => {
      for (const name of readdirSync(dir)) {
        const path = join(dir, name);
        if (statSync(path).isDirectory()) walk(path);
        else if (/\.tsx?$/.test(name)) {
          const source = readFileSync(path, "utf8");
          if (
            /import\s*\{[^}]*\b(si|en)\b[^}]*\}\s*from\s*"[^"]*lib\/strings/.test(source) ||
            /from\s*"[^"]*lib\/(strings|content)\.en"/.test(source)
          ) {
            offenders.push(path);
          }
        }
      }
    };
    walk(join(__dirname, "../src/components"));
    walk(join(__dirname, "../src/app"));
    expect(offenders).toEqual([]);
  });

  it("is a choice in the settings, each language named in itself", async () => {
    const user = userEvent.setup();
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      bookServer(),
    );
    // Once the session is known: the masthead is rebuilt when it is.
    await screen.findByRole("heading", { name: "ඉතිහාසය.pdf" });
    await user.click(screen.getByRole("button", { name: si.settingsToggle }));
    const group = screen.getByRole("group", { name: si.settingsLanguage });

    const sinhala = within(group).getByRole("radio", { name: "සිංහල" });
    const english = within(group).getByRole("radio", { name: "English" });
    expect((sinhala as HTMLInputElement).checked).toBe(true);
    expect(within(group).getByText("English").getAttribute("lang")).toBe("en");
    expect(within(group).getByText("සිංහල").getAttribute("lang")).toBe("si");

    await user.click(english);
    // Remembered where the server will read it, and the page re-rendered there.
    expect(document.cookie).toContain(`${LOCALE_COOKIE}=en`);
    expect(navigations).toContain("refresh");
  });

  it("shows the reader's current language as chosen", async () => {
    const user = userEvent.setup();
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      bookServer(),
      undefined,
      "en",
    );
    await screen.findByRole("heading", { name: "ඉතිහාසය.pdf" });
    await user.click(screen.getByRole("button", { name: en.settingsToggle }));
    const group = screen.getByRole("group", { name: en.settingsLanguage });
    expect(
      (within(group).getByRole("radio", { name: "English" }) as HTMLInputElement).checked,
    ).toBe(true);
  });

  afterEach(() => {
    document.cookie = `${LOCALE_COOKIE}=; path=/; max-age=0`;
  });
});

describe("text a person typed", () => {
  it("is marked by its script", () => {
    expect(scriptLang("ඉතිහාසය")).toBe("si");
    expect(scriptLang("History 10")).toBe("en");
    expect(scriptLang("ඉතිහාසය 10 History")).toBe("si");
    expect(scriptLang("2026")).toBeUndefined();
  });
});

function bookServer() {
  return new FakeServer({
    books: [
      {
        document_id: "doc-1",
        filename: "ඉතිහාසය.pdf",
        version: "v1",
        pages: [readablePage(0, ["පළමු වාක්‍යය.", "දෙවන වාක්‍යය."])],
      },
    ],
  });
}

describe("the book, in the English interface", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
  });

  it("keeps every sentence marked as Sinhala", async () => {
    renderApp(
      <AppFrame>
        <Reader documentId="doc-1" />
      </AppFrame>,
      bookServer(),
      undefined,
      "en",
    );
    const sentence = await screen.findByRole("button", { name: "පළමු වාක්‍යය." });
    expect(within(sentence).getByText("පළමු වාක්‍යය.").getAttribute("lang")).toBe("si");
    // And the title, which the reader typed in Sinhala.
    expect(screen.getByRole("heading", { level: 1 }).querySelector('[lang="si"]')).not.toBeNull();
  });

  it("keeps a quiz's question and options marked as Sinhala around English controls", async () => {
    const user = userEvent.setup();
    const server = new FakeServer({
      books: [
        {
          document_id: "doc-1",
          filename: "ඉතිහාසය.pdf",
          version: "v1",
          pages: [readablePage(0, ["ශ්‍රී ලංකාවේ අගනුවර කෝට්ටේ වේ.", "කොළඹ ප්‍රධාන වරාය නගරයයි."])],
        },
      ],
    });
    renderApp(<Practice documentId="doc-1" />, server, undefined, "en");
    await user.click(await screen.findByRole("button", { name: en.makeQuiz }));
    await screen.findByRole("heading", { name: en.questionOf(1, 2) });
    const group = screen.getByRole("group");
    // The question itself, the fieldset's legend, is the book's sentence.
    expect(group.querySelector("legend [lang='si']")).not.toBeNull();
    for (const radio of within(group).getAllByRole("radio")) {
      const option = radio.closest("label")!.querySelector("span");
      expect(option?.getAttribute("lang")).toBe("si");
    }
    expect(screen.getByRole("button", { name: en.checkAnswer })).toBeTruthy();
  });
});

/** As in a11y.test.tsx: contrast needs a real layout, and is checked in the browser. */
async function violationsIn(element: HTMLElement) {
  const results = await axe.run(element, {
    runOnly: {
      type: "tag",
      values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"],
    },
    rules: { "color-contrast": { enabled: false } },
  });
  return results.violations.map((violation) => ({
    id: violation.id,
    nodes: violation.nodes.map((node) => node.html),
  }));
}

describe("no automatically detectable violations in English", () => {
  beforeEach(() => {
    document.documentElement.lang = "en";
  });

  it("on the library, with the settings open", async () => {
    const user = userEvent.setup();
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      bookServer(),
      undefined,
      "en",
    );
    await screen.findByRole("heading", { name: "ඉතිහාසය.pdf" });
    expect(await violationsIn(container)).toEqual([]);

    await user.click(screen.getByRole("button", { name: en.settingsToggle }));
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on a page being read", async () => {
    const user = userEvent.setup();
    const { container } = renderApp(
      <AppFrame>
        <Reader documentId="doc-1" />
      </AppFrame>,
      bookServer(),
      undefined,
      "en",
    );
    const sentence = await screen.findByRole("button", { name: "පළමු වාක්‍යය." });
    expect(await violationsIn(container)).toEqual([]);
    await user.click(sentence);
    await waitFor(() => expect(sentence.getAttribute("aria-current")).toBe("true"));
    expect(await violationsIn(container)).toEqual([]);
  });

  it("on the bookmarks screen", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Bookmarks />
      </AppFrame>,
      bookServer(),
      undefined,
      "en",
    );
    await screen.findByRole("heading", { name: en.bookmarksEmptyTitle });
    expect(await violationsIn(container)).toEqual([]);
  });

  it("when signed out", async () => {
    const { container } = renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      new FakeServer(),
      "",
      "en",
    );
    await screen.findByRole("heading", { name: en.signedOutHeading });
    expect(await violationsIn(container)).toEqual([]);
  });
});

describe("the helpers take the reader's dictionary", () => {
  it("so English words come from English", () => {
    expect(stringsFor("en")).toBe(en);
    expect(stringsFor("si")).toBe(si);
  });
});
