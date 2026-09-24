import type { ReactNode } from "react";

import type { ProsePage } from "@/lib/content";
import { REPORT_URL } from "@/lib/content";
import { strings } from "@/lib/strings";

/**
 * A public page of prose: one h1, a lead, and a section per h2.
 *
 * Built for reading by heading. Each section is a real `<section>` named by
 * its heading, so a screen reader's list of regions and its list of headings
 * both give the page's outline. A server component: nothing here runs in the
 * browser, so the page renders statically and reads with scripts off.
 */
export function ProsePageView({
  page,
  report = false,
  children,
}: {
  page: ProsePage;
  /** Offer the way to report a barrier at the end. */
  report?: boolean;
  /** Anything the page adds after its sections. */
  children?: ReactNode;
}) {
  return (
    <article className="prose-page">
      <h1>{page.title}</h1>
      <p className="prose-lead">{page.lead}</p>

      {page.sections.map((section, index) => {
        const id = `section-${index}`;
        return (
          <section key={section.heading} aria-labelledby={id}>
            <h2 id={id}>{section.heading}</h2>
            {section.paragraphs?.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
            {section.list ? (
              <ul>
                {section.list.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
          </section>
        );
      })}

      {children}

      {report ? (
        <p>
          <a className="btn" href={REPORT_URL} rel="noopener noreferrer">
            {strings.reportBarrier}
          </a>
        </p>
      ) : null}

      {page.reviewed ? <p className="hint">{strings.lastReviewed(page.reviewed)}</p> : null}
    </article>
  );
}
