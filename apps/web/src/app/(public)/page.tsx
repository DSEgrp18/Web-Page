import type { Metadata } from "next";
import Link from "next/link";
import type { ComponentType } from "react";

import {
  AnswerIcon,
  ArrowRightIcon,
  CheckIcon,
  HeadphonesIcon,
  PlayIcon,
  PractiseIcon,
  TrackIcon,
} from "@/components/Icons";
import { contentFor } from "@/lib/content";
import { stringsFor } from "@/lib/i18n";
import { getLocale, getStrings } from "@/lib/i18n.server";

/**
 * The front door, for someone who has not signed in: what Swara is, the four
 * steps of studying with it, who it is for, and the two ways in.
 *
 * A reader who has signed in never sees it: `src/proxy.ts` sends them to
 * `/library` before this renders. No autoplay and no video, as the plan
 * requires: a page that speaks the moment it opens talks over the screen
 * reader that is trying to tell its reader where they are. What moves here
 * moves once, briefly, as the page arrives or a section scrolls in, and not
 * at all for a reader who asked their system for less motion.
 *
 * The photographs and the picture of the player are decoration. Everything
 * they suggest, the page says in words, so they are hidden from assistive
 * technology and carry no text a reader would need.
 *
 * The title is spelled out with `absolute` because this page shares the root
 * layout's segment, where the `%s — ස්වර` template does not apply.
 */
export async function generateMetadata(): Promise<Metadata> {
  const strings = await getStrings();
  return { title: { absolute: `${strings.homeTitle} — ${strings.appName}` } };
}

/** One icon per step of the loop, in the order the steps are written. */
const STEP_ICONS: ComponentType<{ size?: number }>[] = [
  HeadphonesIcon,
  AnswerIcon,
  PractiseIcon,
  TrackIcon,
];

/** The bars of the player's picture: a speaking voice, not a flat line. */
const WAVE = [
  6, 11, 18, 9, 14, 22, 16, 8, 12, 20, 26, 15, 9, 17, 23, 12, 7, 13, 19, 10, 6, 11, 16, 8,
];

export default async function LandingPage() {
  const locale = await getLocale();
  const strings = stringsFor(locale);
  const { landing } = contentFor(locale);
  const [listen, understand, practise] = landing.steps;

  return (
    <div className="lp">
      {/* -- hero ---------------------------------------------------------- */}
      <section className="lp-hero" aria-labelledby="lp-title">
        <div className="lp-hero-copy">
          <p className="lp-eyebrow">{strings.homeTitle}</p>
          <h1 id="lp-title" className="lp-title">
            {landing.tagline}
          </h1>
          <p className="lp-lead">{landing.lead}</p>
          <div className="lp-actions">
            <Link className="btn btn-primary btn-lg lp-cta-main" href="/register">
              <span>{strings.registerHeading}</span>
              <ArrowRightIcon size={20} />
            </Link>
            <Link className="btn btn-lg" href="/sign-in">
              {strings.signInAction}
            </Link>
          </div>
          <nav className="lp-path" aria-label={landing.stepsHeading}>
            <ol>
              {landing.steps.map((step, index) => {
                const Icon = STEP_ICONS[index]!;
                return (
                  <li key={step.title}>
                    <a href={`#step-${index + 1}`}>
                      <span className="lp-path-stop" aria-hidden="true">
                        <Icon size={20} />
                      </span>
                      <span className="lp-path-name">{step.title}</span>
                    </a>
                  </li>
                );
              })}
            </ol>
          </nav>
        </div>

        <div className="lp-hero-art" aria-hidden="true">
          <div className="lp-orb lp-orb-orange" />
          <div className="lp-orb lp-orb-blue" />
          <figure className="lp-photo lp-photo-main">
            <img
              src="/images/reading-desk-1600.webp"
              srcSet="/images/reading-desk-800.webp 800w, /images/reading-desk-1600.webp 1600w"
              sizes="(max-width: 60em) 92vw, 46vw"
              alt=""
              width={1600}
              height={1067}
              fetchPriority="high"
              decoding="async"
            />
          </figure>
          <figure className="lp-photo lp-photo-side">
            <img
              src="/images/study-notebook-540.webp"
              srcSet="/images/study-notebook-540.webp 540w, /images/study-notebook-900.webp 900w"
              sizes="(max-width: 60em) 40vw, 18vw"
              alt=""
              width={540}
              height={745}
              decoding="async"
            />
          </figure>

          <div className="lp-float lp-float-player">
            <span className="lp-play">
              <PlayIcon size={22} />
            </span>
            <div className="lp-float-body">
              <p className="lp-float-label">{listen?.title}</p>
              <p className="lp-float-text">{landing.heroSample}</p>
              <div className="lp-wave">
                {WAVE.map((height, index) => (
                  <span key={index} style={{ blockSize: `${height}px` }} />
                ))}
              </div>
            </div>
          </div>

          <div className="lp-float lp-float-answer">
            <span className="lp-float-icon">
              <AnswerIcon size={18} />
            </span>
            <span className="lp-float-label">{understand?.title}</span>
            <span className="lp-cite">{strings.citationPage("12")}</span>
          </div>

          <div className="lp-float lp-float-practise">
            <span className="lp-float-icon lp-float-icon-ok">
              <CheckIcon size={18} />
            </span>
            <span className="lp-float-label">{practise?.title}</span>
          </div>
        </div>
      </section>

      {/* -- the learning loop -------------------------------------------- */}
      <section className="lp-section" aria-labelledby="landing-steps">
        <header className="lp-section-head">
          <p className="lp-kicker">{strings.howItWorksNav}</p>
          <h2 id="landing-steps">{landing.stepsHeading}</h2>
        </header>
        <ol className="lp-steps">
          {landing.steps.map((step, index) => {
            const Icon = STEP_ICONS[index]!;
            return (
              <li
                key={step.title}
                id={`step-${index + 1}`}
                className="lp-step"
                data-ready={step.ready}
              >
                <span className="lp-step-icon">
                  <Icon size={22} />
                </span>
                <span className="lp-step-number latin" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div className="lp-step-copy">
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
                </div>
                {index === 0 ? (
                  <img
                    className="lp-step-photo"
                    src="/images/colour-book-900.webp"
                    srcSet="/images/colour-book-540.webp 540w, /images/colour-book-900.webp 900w"
                    sizes="(max-width: 60em) 92vw, 42vw"
                    alt=""
                    width={540}
                    height={729}
                    loading="lazy"
                    decoding="async"
                  />
                ) : null}
              </li>
            );
          })}
        </ol>
      </section>

      {/* -- who it is for -------------------------------------------------- */}
      <section className="lp-section" aria-labelledby="landing-for">
        <header className="lp-section-head">
          <p className="lp-kicker">{strings.appName}</p>
          <h2 id="landing-for">{landing.forHeading}</h2>
        </header>
        <div className="lp-audience">
          <article className="lp-audience-card">
            <div className="lp-audience-photo">
              <img
                src="/images/student-laptop-700.webp"
                srcSet="/images/student-laptop-700.webp 700w, /images/student-laptop-1400.webp 1400w"
                sizes="(max-width: 60em) 92vw, 44vw"
                alt=""
                width={700}
                height={491}
                loading="lazy"
                decoding="async"
              />
            </div>
            <div className="lp-audience-body">
              <h3>{landing.audienceStudents}</h3>
              <p>{landing.forBody[0]}</p>
              <Link className="lp-link" href="/how-it-works">
                <span>{strings.howItWorksNav}</span>
                <ArrowRightIcon size={18} />
              </Link>
            </div>
          </article>
          <article className="lp-audience-card">
            <div className="lp-audience-photo">
              <img
                src="/images/classroom-800.webp"
                srcSet="/images/classroom-800.webp 800w, /images/classroom-1600.webp 1600w"
                sizes="(max-width: 60em) 92vw, 44vw"
                alt=""
                width={800}
                height={533}
                loading="lazy"
                decoding="async"
              />
            </div>
            <div className="lp-audience-body">
              <h3>{strings.forTeachersNav}</h3>
              <p>{landing.forBody[1]}</p>
              <Link className="lp-link" href="/for-teachers">
                <span>{strings.forTeachersNav}</span>
                <ArrowRightIcon size={18} />
              </Link>
            </div>
          </article>
        </div>
      </section>

      {/* -- the way in ----------------------------------------------------- */}
      <section className="lp-closing" aria-labelledby="lp-closing-title">
        <div className="lp-closing-copy">
          <img
            className="lp-closing-logo"
            src="/brand/swara-lockup-dark.webp"
            alt=""
            width={528}
            height={140}
            loading="lazy"
            decoding="async"
          />
          <h2 id="lp-closing-title">{strings.appTagline}</h2>
          <p>{landing.lead}</p>
          <div className="lp-actions">
            <Link className="btn btn-accent btn-lg lp-cta-main" href="/register">
              <span>{strings.registerHeading}</span>
              <ArrowRightIcon size={20} />
            </Link>
            <Link className="btn btn-on-navy btn-lg" href="/sign-in">
              {strings.signInAction}
            </Link>
          </div>
        </div>
        <div className="lp-closing-art" aria-hidden="true">
          <img
            src="/images/student-tablet-560.webp"
            srcSet="/images/student-tablet-560.webp 560w, /images/student-tablet-1000.webp 1000w"
            sizes="(max-width: 60em) 0px, 30vw"
            alt=""
            width={560}
            height={789}
            loading="lazy"
            decoding="async"
          />
        </div>
      </section>
    </div>
  );
}
