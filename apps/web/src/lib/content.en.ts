/**
 * The public pages in English: the optional second language.
 *
 * Translated from `content.ts`, which is the text of record. The privacy
 * notice, the terms and the accessibility statement are marked `draft`: each
 * shows a notice saying it is a translation awaiting review and that the
 * Sinhala applies where they differ. None of them has had the legal review a
 * service used by minors needs (CLAUDE.md, "Privacy and deployment").
 */

import type { Content, ProsePage } from "./content";

const howItWorks: ProsePage = {
  title: "How it works",
  lead: "Swara has two modes, and they never mix: reading the book, and asking about it.",
  sections: [
    {
      heading: "Reading: the book's own words",
      paragraphs: [
        'Swara reads only the words of the book you added. No AI model changes, completes or "corrects" them.',
        "Numbers, dates and abbreviations are turned into spoken form for listening only. The screen shows them as the book printed them.",
        "When a scanned page has been read from its image (OCR), the page says it may contain mistakes.",
      ],
    },
    {
      heading: "Asking: answers from the book",
      paragraphs: [
        "You can ask questions about the book in the assistant beside it. It answers from that book only.",
        "Every answer names the page it came from. You can press to go to that sentence.",
        "If the answer is the book's own words, it says so. If a model wrote the answer, it says that plainly too.",
        'When the book has no answer, it says "not found" instead of making one up.',
      ],
    },
    {
      heading: "You are in control",
      list: [
        "Nothing starts reading aloud unless you press a button.",
        "Your place is remembered. You can add bookmarks too.",
        "Speed, text size and colour scheme can be changed in the settings.",
      ],
    },
  ],
};

const forTeachers: ProsePage = {
  title: "For teachers",
  lead: "This page explains how the class features work, and what you can see.",
  sections: [
    {
      heading: "Prepared once, for the whole class",
      paragraphs: [
        "A teacher can prepare a book once and give it to a class. Its audio is made once for every student in the class.",
        "Before publishing, you review the pages marked as needing a check. Pages you withhold are not read to students.",
      ],
    },
    {
      heading: "Your right to share a book",
      paragraphs: [
        "Before giving a book to a class, you confirm that you have the right to. Who confirmed it, and on what basis, is recorded.",
        "Books are shared with your class only. They are never public, and you can withdraw them at any time.",
      ],
    },
    {
      heading: "What you can and cannot see",
      list: [
        "You never see a student's private books, bookmarks, notes or questions.",
        "Class progress shows only for students who chose to share it. It is off unless they turn it on, and a student can withdraw it at any time.",
      ],
    },
    {
      heading: "Getting a teacher account",
      paragraphs: [
        "Nobody can register as a teacher themselves. A teacher account comes from a single-use code given by the team that runs the service.",
      ],
    },
  ],
};

const help: ProsePage = {
  title: "Help",
  lead: "Using Swara with a screen reader, a keyboard or magnification.",
  sections: [
    {
      heading: "With a screen reader",
      list: [
        'Every page starts with a "Skip to content" link.',
        "Pages are organised by headings. Move between parts with the H key in NVDA, or by headings in TalkBack.",
        "When reading a book, every sentence is a button. Pressing it reads from there.",
        "There are no single-letter shortcuts, because they clash with NVDA's navigation keys.",
      ],
    },
    {
      heading: "Seeing the page",
      list: [
        "Change the colour scheme (light, dark) and the text size in the settings.",
        "You can use the browser's zoom. Testing at 400% zoom is not finished yet.",
      ],
    },
    {
      heading: "Your account",
      list: [
        "If you forget your password, set a new one with the recovery code you were given when you created the account.",
        "If you have lost the code as well, tell your teacher or the service team.",
      ],
    },
    {
      heading: "Reporting a problem",
      paragraphs: [
        "If a word is pronounced wrongly, a page has been read wrongly, or there is a part you cannot use, let us know. A way to report it inside Swara is being prepared.",
      ],
    },
  ],
};

const accessibility: ProsePage = {
  title: "Accessibility statement",
  lead: "Swara aims to meet WCAG 2.2 level AA. At present it partially meets it: the limits below still apply.",
  reviewed: "2026-09-24",
  draft: true,
  sections: [
    {
      heading: "Status",
      paragraphs: [
        "Partially conformant. That is, some parts do not yet fully meet WCAG 2.2 level AA.",
        "Automated checks (axe, colour contrast, both colour schemes) run on every change. They do not find every barrier.",
      ],
    },
    {
      heading: "Known limits",
      list: [
        "Testing with real users of NVDA and TalkBack is not finished yet.",
        "The Sinhala words of the interface have not yet been reviewed by a native speaker. The English interface is a draft translation.",
        "Scanned pages (OCR) may contain mistakes. They are marked as needing a check.",
        "Equations, tables, diagrams and images are not described. Only the text in them can be read, and it may be incomplete or out of order.",
        "The reading order of a complex page layout may sometimes be wrong.",
        "On a server without the real Sinhala voice connected, the sound is a demonstration tone. It then says so.",
      ],
    },
    {
      heading: "Reporting a barrier",
      paragraphs: [
        "If you find something you cannot use, tell your teacher, or report it with the link below. Say what you were using (for example NVDA or TalkBack) and what happened.",
      ],
    },
  ],
};

const privacy: ProsePage = {
  title: "Privacy",
  lead: "What Swara stores, when it leaves the server, and how you can remove it.",
  reviewed: "2026-09-24",
  draft: true,
  sections: [
    {
      heading: "What is stored",
      list: [
        "Your account: your name, email address, and a secure hash of your password and recovery code. Your password itself is never stored.",
        "The books you add, the text taken from them, and the audio made for them.",
        "Where you stopped, and your bookmarks.",
        "The questions you ask the assistant are not stored.",
      ],
    },
    {
      heading: "Your books are private",
      paragraphs: [
        "Only you can see your books. Administrators cannot see them either. Your books are not used to train AI models.",
      ],
    },
    {
      heading: "What leaves the server",
      paragraphs: [
        "By default your book does not leave the server: getting the text, reading scanned pages and making the audio all happen on the Swara server itself.",
        "The people who run the service can turn on Google's Gemini service for two tasks: finding a page's structure (headings, paragraphs), when the page's text is sent; and written answers, when your question and the passages found in the book are sent. What is turned on at this server now is shown at the end of this page.",
      ],
    },
    {
      heading: "Removing it",
      paragraphs: [
        "Deleting a book also removes its text, audio, your place in it and its bookmarks. Deleting your account removes all your books and the account.",
        "Signing out or deleting your account also removes the offline audio stored on this device, because phones are shared.",
        "How long backups are kept will be stated here before the service opens to the public.",
      ],
    },
    {
      heading: "What teachers see",
      paragraphs: [
        "A teacher never sees your private books, notes or questions; they see your progress only if you choose to share it.",
      ],
    },
    {
      heading: "Under 18",
      paragraphs: [
        "If you are under 18, a parent's or guardian's agreement is needed before you use Swara. We ask only for what an account needs.",
      ],
    },
  ],
};

const terms: ProsePage = {
  title: "Terms of use",
  lead: "What you agree to when you use Swara.",
  reviewed: "2026-09-24",
  draft: true,
  sections: [
    {
      heading: "The books you add",
      list: [
        "Add only books you have the right to use.",
        "Only you can see your books. Swara does not publish them or share them with others.",
      ],
    },
    {
      heading: "Teachers",
      list: [
        "A teacher who gives a book to a class must confirm they have the right to do so. That confirmation is recorded.",
        "Sharing is limited to the class. There is no public library of books.",
      ],
    },
    {
      heading: "The voice",
      paragraphs: [
        "Swara's Sinhala voice is based on a model licensed for non-commercial use only (Coqui XTTS-v2, under the CPML licence). Swara is therefore a non-commercial educational service, and the audio it makes cannot be sold or used commercially.",
      ],
    },
    {
      heading: "The service",
      paragraphs: [
        "Swara is being developed as a study project. It is provided as it is; getting text from a page and the voice may not always be right.",
      ],
    },
  ],
};

export const enContent: Content = {
  landing: {
    heading: "Swara",
    tagline: "Hear, understand and study Sinhala books",
    lead: "Swara is a Sinhala study platform made for blind and low-vision readers and students. Add your textbook, hear it read aloud, and ask questions about it.",
    stepsHeading: "How you study with Swara",
    steps: [
      {
        title: "Listen",
        body: "Add a book as a PDF, a Word file or a photograph. Swara reads it sentence by sentence. Stop anywhere, and carry on from the same place later.",
        ready: true,
      },
      {
        title: "Understand",
        body: "Ask a question about the book. The answer comes from a passage of the book itself, with a link to the page it is on. When the book has no answer, Swara says so.",
        ready: true,
      },
      {
        title: "Practise",
        body: "Practice questions made from the book's own sentences.",
        ready: true,
      },
      {
        title: "Track your progress",
        body: "The chapters you have heard, and what to revise.",
        ready: true,
      },
    ],
    notYet: "Not yet",
    forHeading: "Who it is for",
    forBody: [
      "Students and readers who use a screen reader (NVDA, TalkBack) or magnification.",
      "Teachers who want to prepare a book once for a whole class.",
    ],
    audienceStudents: "For students and readers",
    heroSample: "All living things are made of cells.",
  },
  howItWorks,
  forTeachers,
  help,
  accessibility,
  privacy,
  terms,
};
