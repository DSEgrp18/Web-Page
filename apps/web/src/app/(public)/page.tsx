import type { Metadata } from "next";
import Link from "next/link";

import { contentFor } from "@/lib/content";
import { stringsFor } from "@/lib/i18n";
import { getLocale, getStrings } from "@/lib/i18n.server";

/**
 * The front door, for someone who has not signed in.
 *
 * A reader who has signed in never sees it: `src/proxy.ts` sends them to
 * `/library` before this renders. No autoplay and no video, as the plan
 * requires: a page that speaks the moment it opens talks over the screen
 * reader that is trying to tell its reader where they are.
 *
 * The title is spelled out with `absolute` because this page shares the root
 * layout's segment, where the `%s — ස්වර` template does not apply.
 */
export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: { absolute: `${strings.homeTitle} — ${strings.appName}` } };
}

export default async function LandingPage() {
  const locale = await getLocale();
  const strings = stringsFor(locale);
  const { landing } = contentFor(locale);
  return (
    <article className="landing">
      <header className="landing-hero">
        <h1>{landing.heading}</h1>
        <p className="landing-tagline">{landing.tagline}</p>
        <p className="prose-lead">{landing.lead}</p>
        <div className="notice-actions">
          <Link className="btn btn-primary" href="/register">
            {strings.registerHeading}
          </Link>
          <Link className="btn" href="/sign-in">
            {strings.signInAction}
          </Link>
        </div>
      </header>

      <section aria-labelledby="landing-steps">
        <h2 id="landing-steps">{landing.stepsHeading}</h2>
        <ol className="landing-steps">
          {landing.steps.map((step) => (
            <li key={step.title} className="card" data-ready={step.ready}>
              <h3>
                {step.title}
                {step.ready ? null : (
                  <>
                    {" "}
                    <span className="pill pill-quiet">{landing.notYet}</span>
                  </>
                )}
              </h3>
              <p>{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="landing-for">
        <h2 id="landing-for">{landing.forHeading}</h2>
        <ul>
          {landing.forBody.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        <p>
          <Link href="/how-it-works">{strings.howItWorksNav}</Link>
        </p>
      </section>
    </article>
  );
}
