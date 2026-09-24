import { render, screen, waitFor, within } from "@testing-library/react";
import axe from "axe-core";
import { NextRequest } from "next/server";
import type { ReactElement } from "react";
import { describe, expect, it } from "vitest";

import nextConfig from "../next.config";
import AccessibilityPage from "../src/app/(public)/accessibility/page";
import ForTeachersPage from "../src/app/(public)/for-teachers/page";
import HelpPage from "../src/app/(public)/help/page";
import HowItWorksPage from "../src/app/(public)/how-it-works/page";
import LandingPage from "../src/app/(public)/page";
import PrivacyPage from "../src/app/(public)/privacy/page";
import TermsPage from "../src/app/(public)/terms/page";
import { AppFrame } from "../src/components/AppFrame";
import { Library } from "../src/components/Library";
import { ProcessingNow } from "../src/components/ProcessingNow";
import { PublicFrame } from "../src/components/PublicFrame";
import { accessibility, landing, privacy, REPORT_URL } from "../src/lib/content";
import { strings } from "../src/lib/strings";
import { proxy, SESSION_COOKIE } from "../src/proxy";
import { FakeServer } from "./fakeApi";
import { renderApp } from "./render";

const PAGES: [string, () => ReactElement][] = [
  ["the landing page", () => <LandingPage />],
  ["how it works", () => <HowItWorksPage />],
  ["for teachers", () => <ForTeachersPage />],
  ["help", () => <HelpPage />],
  ["the accessibility statement", () => <AccessibilityPage />],
  ["the privacy notice", () => <PrivacyPage />],
  ["the terms", () => <TermsPage />],
];

function readinessFetch(answer: Record<string, string> | "fail") {
  return (async () => {
    if (answer === "fail") throw new TypeError("offline");
    return Response.json({ alive: true, ...answer });
  }) as unknown as typeof fetch;
}

describe("the front door", () => {
  it("says what Swara is, and offers the way in", () => {
    render(<LandingPage />);

    expect(screen.getByRole("heading", { level: 1, name: landing.heading })).toBeTruthy();
    expect(screen.getByRole("link", { name: strings.registerHeading }).getAttribute("href")).toBe(
      "/register",
    );
    expect(screen.getByRole("link", { name: strings.signInAction }).getAttribute("href")).toBe(
      "/sign-in",
    );
  });

  it("says plainly which steps are not built yet", () => {
    const { container } = render(<LandingPage />);
    const steps = within(container.querySelector<HTMLElement>(".landing-steps")!);

    const notYet = landing.steps.filter((step) => !step.ready).length;
    expect(steps.getAllByText(landing.notYet)).toHaveLength(notYet);
  });

  it("has no audio or video to start by itself", () => {
    const { container } = render(<LandingPage />);
    expect(container.querySelector("audio, video, iframe")).toBeNull();
  });
});

describe("a returning reader", () => {
  it("is sent from the front door to their books", () => {
    const request = new NextRequest("https://swara.test/", {
      headers: { cookie: `${SESSION_COOKIE}=abc` },
    });

    const response = proxy(request);

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("https://swara.test/library");
  });

  it("while a newcomer stays at the front door", () => {
    const response = proxy(new NextRequest("https://swara.test/"));
    expect(response.headers.get("location")).toBeNull();
  });
});

describe("old addresses", () => {
  it("send a saved reader link, with its sentence, to the library", async () => {
    const redirects = await nextConfig.redirects!();
    const reader = redirects.find((r) => r.source === "/documents/:id");

    expect(reader).toMatchObject({ destination: "/library/:id", permanent: true });
    // Next carries the query string (?segment=) across a redirect by itself.
  });

  it("send the retired study page to the book, where the assistant is", async () => {
    const redirects = await nextConfig.redirects!();
    expect(redirects.find((r) => r.source === "/documents/:id/study")).toMatchObject({
      destination: "/library/:id",
      permanent: true,
    });
  });
});

describe("the public pages", () => {
  it.each(PAGES)("give %s one h1 and a named section per heading", (_name, page) => {
    render(page());
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    for (const heading of screen.queryAllByRole("heading", { level: 2 })) {
      expect(heading.closest("section")?.getAttribute("aria-labelledby")).toBe(heading.id);
    }
  });

  it("says how to report a barrier, and when the statement was last checked", () => {
    render(<AccessibilityPage />);

    expect(screen.getByRole("link", { name: strings.reportBarrier }).getAttribute("href")).toBe(
      REPORT_URL,
    );
    expect(screen.getByText(strings.lastReviewed(accessibility.reviewed!))).toBeTruthy();
  });

  it("states partial conformance, not full", () => {
    render(<AccessibilityPage />);
    expect(screen.getByText(accessibility.lead)).toBeTruthy();
    expect(accessibility.lead).toContain("අර්ධ වශයෙන්");
  });
});

describe("what this server sends out", () => {
  it("says when nothing leaves the server", async () => {
    render(
      <ProcessingNow
        fetchImpl={readinessFetch({
          structure: "deterministic",
          answers: "extractive",
          ocr: "broken",
        })}
      />,
    );

    await waitFor(() => expect(screen.getAllByText(strings.processingHere)).toHaveLength(3));
    expect(screen.queryByText(strings.processingGoogle)).toBeNull();
  });

  it("says when Google receives page text or passages", async () => {
    render(
      <ProcessingNow
        fetchImpl={readinessFetch({ structure: "gemini", answers: "gemini", ocr: "off" })}
      />,
    );

    await waitFor(() => expect(screen.getAllByText(strings.processingGoogle)).toHaveLength(2));
    expect(screen.getByText(strings.processingOff)).toBeTruthy();
  });

  it("does not guess when it cannot ask", async () => {
    render(<ProcessingNow fetchImpl={readinessFetch("fail")} />);

    expect(await screen.findByText(strings.processingNowUnknown)).toBeTruthy();
  });

  it("is part of the privacy notice", () => {
    render(<PrivacyPage />);
    expect(screen.getByRole("heading", { name: strings.processingNowHeading })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 1, name: privacy.title })).toBeTruthy();
  });
});

describe("the frames", () => {
  it("offer a newcomer the way in", async () => {
    renderApp(
      <PublicFrame>
        <p>content</p>
      </PublicFrame>,
      new FakeServer(),
      "",
    );

    expect(await screen.findByRole("link", { name: strings.registerHeading })).toBeTruthy();
    expect(screen.queryByRole("link", { name: strings.libraryHeading })).toBeNull();
  });

  it("offer a signed-in reader the way back to their books", async () => {
    renderApp(
      <PublicFrame>
        <p>content</p>
      </PublicFrame>,
      new FakeServer(),
    );

    const back = await screen.findByRole("link", { name: strings.libraryHeading });
    expect(back.getAttribute("href")).toBe("/library");
  });

  it("put the statements one link away from every page, the app included", async () => {
    renderApp(
      <AppFrame>
        <Library />
      </AppFrame>,
      new FakeServer(),
    );

    const footer = within(
      await screen.findByRole("navigation", { name: strings.footerNavigation }),
    );
    expect(footer.getByRole("link", { name: strings.accessibilityNav }).getAttribute("href")).toBe(
      "/accessibility",
    );
    expect(footer.getByRole("link", { name: strings.privacyNav })).toBeTruthy();
    expect(footer.getByRole("link", { name: strings.termsNav })).toBeTruthy();
  });
});

describe("no automatically detectable violations", () => {
  it.each(PAGES)("on %s", async (_name, page) => {
    document.documentElement.lang = "si";
    renderApp(<PublicFrame>{page()}</PublicFrame>, new FakeServer(), "");
    await screen.findAllByRole("link", { name: strings.registerHeading });

    const results = await axe.run(document.body, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
      rules: { "color-contrast": { enabled: false } },
    });
    expect(results.violations.map((v) => `${v.id}: ${v.nodes[0]?.html}`)).toEqual([]);
  });
});
