/**
 * Every word the interface says, in English.
 *
 * Sinhala is the primary interface language and the default (CLAUDE.md);
 * this is the optional second one. Same keys as `strings.ts`, and the type
 * makes that so: a key missing here, or one here that Sinhala does not have,
 * fails the build, and `tests/i18n.test.ts` checks the shapes match too.
 *
 * Written from the Sinhala, not the other way round. Where the Sinhala has
 * been chosen for a screen reader (distinct names for controls that would
 * otherwise share one), the English keeps the distinction.
 */

import type { Strings } from "./strings";

/** "1 page", "2 pages": English counts, where Sinhala needs no plural. */
function n(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? "" : "s"}`;
}

export const en: Strings = {
  appName: "Swara",
  appNameLatin: "Swara",
  appTagline: "Read, hear and understand Sinhala books",

  // -- account -----------------------------------------------------------
  signInHeading: "Sign in",
  signInAction: "Sign in",
  registerHeading: "Create an account",
  registerAction: "Create account",
  recoverHeading: "Recover your account",
  recoverIntro:
    "Set a new password with the recovery code you were given when you created your account. No email is needed.",
  recoverAction: "Set new password",
  emailLabel: "Email address",
  passwordLabel: "Password",
  newPasswordLabel: "New password",
  passwordHint: (min: number) => `At least ${n(min, "character")}.`,
  showPassword: "Show password",
  showPasswordForChange: "Change password: show current password",
  showPasswordForChangeNew: "Change password: show new password",
  showPasswordForRecovery: "Recovery code: show current password",
  showPasswordForDelete: "Delete account: show current password",
  displayNameLabel: "Your name",
  displayNameHint: "The name Swara calls you by.",
  recoveryCodeLabel: "Recovery code",
  recoveryCodeHint:
    "Spaces and dashes between the characters do not matter, nor does upper or lower case. A code from your teacher goes here too.",
  signedOutHeading: "Sign in to read your books",
  signedOutBody: "Only you can see your books. Sign in to your account to open them.",
  noAccountYet: "No account yet?",
  haveAccount: "Already have an account?",
  forgotPassword: "Forgotten your password?",
  signOut: "Sign out",
  signedOut: "You have signed out.",
  signedIn: "You have signed in.",
  loadingSession: "Loading…",
  accountHeading: "My account",
  accountDetails: "Account details",
  roleTerm: "Role",
  roleName: (role: string) =>
    role === "teacher" ? "Teacher" : role === "admin" ? "Administrator" : "Student",
  currentPasswordLabel: "Current password",
  changePasswordCurrentLabel: "Change password — current password",
  recoveryPasswordCurrentLabel: "Recovery code — current password",
  deletePasswordCurrentLabel: "Delete account — current password",
  changePasswordHeading: "Change password",
  changePasswordAction: "Change password",
  passwordChanged: "Password changed. You have been signed out on your other devices.",
  errorWrongPassword: "The current password is not right.",
  recoveryHeading: "Recovery code",
  recoveryMissing:
    "Your account has no recovery code. Make one, so you can get back in if you forget your password.",
  recoveryReplaceIntro: "Making a new code stops the old one working.",
  newRecoveryAction: "Make a new recovery code",
  backToAccount: "Back to my account",
  everywhereHeading: "Sign out everywhere",
  everywhereIntro:
    "If you are signed in on a shared or lost phone, this signs you out there as well as here.",
  everywhereAction: "Sign out everywhere",
  signedOutEverywhere: "You have signed out on every device.",
  deleteAccountHeading: "Delete account",
  deleteAccountIntro:
    "Your account and all your books, audio, notes and bookmarks are removed. This cannot be undone.",
  deleteAccountAction: "Delete account",
  deleteAccountConfirmTitle: "Delete your account?",
  deleteAccountConfirmBody:
    "All your books and everything made from them are removed for good. This cannot be undone.",
  accountDeleted: "Your account has been deleted.",
  // -- classes -------------------------------------------------------------
  classesNav: "Classes",
  progressNav: "Progress",
  offlineNav: "Saved chapters",
  offlineHeading: "Chapters saved to hear offline",
  offlineHow:
    "These are saved on this device only. They are all cleared when you sign out, because phones are shared.",
  offlineUnsupported: "This browser cannot save chapters to hear offline.",
  offlineNothing: "Nothing is saved yet. In a book, choose “Save this chapter”.",
  offlineSpace: (used: string, quota: string) =>
    `This site is using ${used} of ${quota} megabytes.`,
  offlineSize: (sentences: number, size: string) =>
    `${n(sentences, "sentence")}, ${size} megabytes.`,
  offlineMissing: (count: number) =>
    count === 1 ? "1 sentence has no audio." : `${n(count, "sentence")} have no audio.`,
  offlineListen: "Listen",
  offlineRemove: "Remove",
  offlineRemoved: (name: string) => `${name} removed.`,
  offlineBack: "Back to saved chapters",
  offlineNoAudio: "No audio",
  offlineSave: "Save this chapter",
  offlineSaving: "Saving the chapter.",
  offlineProgress: (done: number, total: number) => `${done} of ${n(total, "sentence")} saved.`,
  offlineSaved: (ready: number, total: number) =>
    ready === total
      ? `Chapter saved: all ${n(total, "sentence")}.`
      : `Chapter saved: ${ready} of ${n(total, "sentence")}. The rest have no audio yet.`,
  offlineNoneVoiced:
    "No sentence in this chapter has audio yet. Listen to it once, or let your teacher prepare the audio, then try again.",
  pasteLink: "Paste text",
  pasteHeading: "Paste text to read",
  pasteHow:
    "Paste up to 200,000 characters. It is read in sections of about 3,000 characters, not pages. Text in an old font encoding (such as FM-Abhaya) is not converted, and is marked for review.",
  pasteTitleLabel: "Name (optional)",
  pasteTextLabel: "Text",
  pasteAction: "Prepare to read",
  pasteEmpty: "There is no text to paste.",
  pasteStarted: "Preparing the text to read.",
  pasteTooLong: (count: number) =>
    `The text is ${count.toLocaleString("en")} characters; the most is 200,000.`,
  sectionWord: "Section",
  ofSections: (index: number, total: number) => `${index} of ${total} sections`,
  previousSection: "Previous section",
  nextSection: "Next section",
  searchLink: "Search the book",
  searchHeading: (title: string) => `Search in ${title}`,
  searchLabel: "Words to find",
  searchAction: "Search",
  searchHow:
    "A result opens the book at that sentence. It does not start playing, and your place does not change.",
  searchExactHeading: (count: number) => `${n(count, "sentence")} with these words`,
  searchRelatedHeading: "Related passages",
  searchNothing: "Nothing was found.",
  searchFound: (exact: number, related: number) =>
    `Found ${n(exact, "sentence")} and ${related} related passages.`,
  searchResultPage: (label: string) => `Page ${label}`,
  reportLink: "Report a problem",
  reportSentenceLink: "Report a problem with this sentence",
  reportQuestionLink: "Report a problem with this question",
  reportInApp: "Report it from your account",
  reportHeading: "Report a problem",
  reportKindLegend: "What is the problem?",
  reportKinds: {
    pronunciation: "Wrong pronunciation",
    extraction: "Text wrong or missing",
    question: "Question wrong",
    accessibility: "Accessibility barrier",
    other: "Other",
  } as Record<string, string>,
  reportMessageLabel: "Details",
  reportMessageRequired: "Describe the problem briefly.",
  reportSend: "Send",
  reportSent: "Thank you. Your report has been sent.",
  reportWhoBook: "The book's owner sees this. Your name is not shown.",
  reportWhoSite: "This goes to the people who run the service.",
  reportAboutBook: "Book:",
  reportAboutSentence: (sentence: string) => `Sentence: ${sentence}`,
  markReportHandled: "Mark as handled",
  reportMarkedHandled: "Report marked as handled.",
  reportHandled: "Marked as handled.",
  reportsLink: "Reported problems",
  reportsHeading: (title: string) => `${title} — reported problems`,
  reportsNone: "No problems have been reported yet.",
  reportsSentence: (sentence: string) => `Sentence: ${sentence}`,
  reportsQuestion: "About a question",
  progressHeading: "My progress",
  progressSummary: (complete: number, chapters: number, due: number) =>
    `You have heard ${complete} of ${n(chapters, "chapter")} in full; ${due === 1 ? "1 question is" : `${n(due, "question")} are`} due for revision today.`,
  progressNoBooks: "No books yet. Once you add a book, your progress shows here.",
  progressCaption: (title: string) => `${title} — by chapter`,
  progressChapter: "Chapter",
  progressHeard: "Heard",
  progressAnswered: "Answered correctly",
  progressDue: "Due for revision",
  progressWholeBook: "Whole book",
  progressOpening: "Before the first chapter",
  progressHeardCell: (heard: number, sentences: number) =>
    sentences === 0 ? "—" : `${Math.round((heard / sentences) * 100)}%`,
  progressAnsweredCell: (correct: number, answered: number) =>
    answered === 0 ? "—" : `${correct} of ${answered}`,
  reviseHeading: "Revise next",
  reviseNothing: "No questions are due for revision today.",
  reviseLink: (title: string, due: number) => `${title} — ${n(due, "question")}`,
  reviewingDue: (count: number) => `${n(count, "question")} due for revision.`,
  classProgressHeading: "Students' progress",
  classProgressHow:
    "Only students who chose to share their progress appear here, and only for books shared with this class.",
  classProgressNobody: "No student has shared their progress yet.",
  classNotSharing: (count: number) =>
    count === 1
      ? "1 student does not share their progress."
      : `${n(count, "student")} do not share their progress.`,
  classProgressDownload: "Download as a spreadsheet",
  classProgressNoBooks: "No books are shared with this class.",
  classesHeading: "My classes",
  joinHeading: "Join a class",
  joinCodeLabel: "Class code",
  joinCodeHint: "The eight-digit code your teacher gave you. Spaces and dashes do not matter.",
  shareProgressLabel: "Show my progress to my teacher",
  shareProgressHint:
    "Off unless you turn it on, and you can change it at any time. Your books, notes and questions are never shown.",
  joinAction: "Join",
  joinedWaiting: (name: string) =>
    `Request sent to "${name}". You will see the class's books once your teacher approves it.`,
  errorNoClassCode: "There is no class with that code. Check the code and try again.",
  joinedHeading: "Classes you are in",
  noJoined: "You are not in any class yet.",
  memberState: (state: string) =>
    state === "active" ? "Member" : state === "removed" ? "Removed" : "Waiting for approval",
  teacherOf: (name: string) => `Teacher: ${name}`,
  progressShared: "Progress shown to your teacher.",
  progressPrivate: "Progress is yours alone.",
  leaveClass: "Leave the class",
  leftClass: "You have left the class.",
  teachingHeading: "Classes you teach",
  createClassLabel: "New class name",
  createClassAction: "Create class",
  classCreated: "Class created.",
  noTaught: "You have not created any classes yet.",
  memberCounts: (active: number, pending: number) =>
    `${n(active, "student")}, ${pending} waiting for approval`,
  classCodeHeading: "Class code",
  classCodeHint:
    "Give this code to your students. They will not see the class's books until you approve them.",
  newCodeAction: "Make a new code",
  newCodeDone: "New code made. The old code no longer works.",
  membersHeading: "Students",
  noMembers: "Nobody has joined yet.",
  memberColName: "Name",
  memberColState: "Status",
  memberColShares: "Shares progress",
  memberColActions: "Actions",
  yes: "Yes",
  no: "No",
  approveNamed: (name: string) => `Approve ${name}`,
  removeNamed: (name: string) => `Remove ${name}`,
  memberApproved: (name: string) => `${name} approved.`,
  memberRemoved: (name: string) => `${name} removed.`,
  resetNamed: (name: string) => `A password reset code for ${name}`,
  resetConfirmTitle: (name: string) => `Make a password reset code for ${name}?`,
  resetConfirmBody:
    'The code works once, within 30 minutes. Their own recovery code still works. Their password does not change until they use this code with their own email address on the "Recover your account" page. They will be told that you made the code.',
  resetConfirmAction: "Make the code",
  resetCodeHeading: (name: string) => `Code for ${name}`,
  resetCodeIntro:
    'Give this to them privately. It is not shown again, and it expires in 30 minutes. They use it with their own email address on the "Recover your account" page.',
  resetIssued: (name: string) => `A code was made for ${name}.`,
  resetDone: "Done",
  resetNoticeHeading: "A notice about your account",
  resetNoticeText: (teacher: string | null, when: string, used: boolean) =>
    `${teacher ? `Your teacher ${teacher}` : "One of your teachers"} made a password reset code for your account ${when}. ` +
    (used ? "Your password has been changed with that code. " : "It has not been used yet. ") +
    "If you did not ask for it, tell your teacher or the service team.",
  resetNoticeSeen: "Understood",
  formatDateTime: (year: number, month: number, day: number, hour: number, minute: number) => {
    const months = [
      "January",
      "February",
      "March",
      "April",
      "May",
      "June",
      "July",
      "August",
      "September",
      "October",
      "November",
      "December",
    ] as const;
    const h = hour % 12 || 12;
    const ampm = hour < 12 ? "am" : "pm";
    const mm = String(minute).padStart(2, "0");
    return `${months[month] ?? month + 1} ${day}, ${year}, ${h}:${mm} ${ampm}`;
  },
  renameClassLabel: "Class name",
  renameClassAction: "Save name",
  classRenamed: "Class renamed.",
  deleteClassAction: "Delete class",
  deleteClassConfirmTitle: "Delete this class?",
  deleteClassConfirmBody:
    "Every student is removed from the class, and books shared with it are no longer shown to them. Their own books are not affected.",
  classDeleted: "Class deleted.",
  backToClasses: "Back to classes",
  fromYourClasses: "From your classes",
  classBookFrom: (name: string) => `From ${name}`,
  // -- sharing a book with a class --------------------------------------------
  shareBook: "Share with a class",
  shareHeading: (title: string) => `Sharing "${title}"`,
  reviewHeading: "Pages to check",
  reviewIntro:
    "These pages were read from an image, so they may contain mistakes. Accept each page, or withhold it. Withheld pages are not read to your class.",
  noReview: "No pages need checking.",
  pageAccept: "Accept",
  pageWithhold: "Withhold",
  openFlaggedPage: (label: string) => `Open page ${label}`,
  savePageDecision: "Save this decision",
  pageDecisionSaved: "The page decision was saved.",
  undecidedCount: (count: number) => `${n(count, "page")} not decided yet`,
  basisHeading: "Your right to share",
  basisIntro:
    "Why do you have the right to share this book with your class? Your answer is recorded.",
  basisName: (basis: string) =>
    ({
      public_domain: "It is out of copyright",
      government_textbook: "It is a government textbook",
      publisher_permission: "I have the publisher's permission",
      own_work: "It is my own work",
      other: "Other",
    })[basis] ?? basis,
  basisNoteLabel: "Details",
  basisNoteHint: 'Needed if you choose "Other".',
  shareClassesLegend: "Classes to share with",
  noClassesToShare: "Create a class first.",
  publishAction: "Share",
  published: "The book is shared with the class.",
  errorUnreviewed: "First decide on every page that needs checking.",
  errorBasisNote: 'Write the details for "Other".',
  errorChooseClass: "Choose at least one class.",
  errorChooseBasis: "Choose your right to share.",
  sharedWithHeading: "Shared with now",
  notShared: "Not shared with any class yet.",
  stopSharingNamed: (name: string) => `Stop sharing with ${name}`,
  stoppedSharing: "Sharing stopped.",
  staleShare:
    "The book has changed since you shared it. The class still reads the earlier version. Share it again to give them the new one.",
  // -- practice ---------------------------------------------------------------
  practiceLink: "Practise",
  practiceHeading: (title: string) => `Practice questions for "${title}"`,
  practiceHow:
    "These questions are the book's own sentences with one word taken out. You can hear where in the book each one comes from.",
  quizzesHeading: "Question sets",
  makeDraftedQuiz: "Draft questions with a model",
  draftedHow:
    "Drafting questions with a model sends passages of the book to an outside service. Every question is checked against a sentence of the book, and any that do not match are discarded.",
  quizGenerating: "The model is drafting questions. This can take a few minutes.",
  quizFailed:
    "The model could not draft questions. You can make questions from the book's own sentences instead.",
  quizDraftedLabel: "Drafted by a model, checked against the book",
  noQuizzes: "No question sets yet.",
  makeQuiz: "Make practice questions",
  makeClassQuiz: "Make questions for the class",
  quizMade: "Questions made.",
  quizName: (count: number, forClass: boolean) =>
    forClass ? `${n(count, "question")} for the class` : `${n(count, "question")} of mine`,
  quizDraft: "Draft: students cannot see it yet.",
  quizStale: "The book has changed since these questions were made.",
  startQuiz: "Start",
  reviewQuiz: "Review",
  deleteQuiz: "Delete",
  quizDeleted: "Question set deleted.",
  questionOf: (index: number, total: number) => `Question ${index} of ${total}`,
  blankWord: "blank",
  checkAnswer: "Check",
  chooseAnswer: "Choose an answer first.",
  rightAnswer: "Right.",
  wrongAnswer: (answer: string) => `Not right. The answer is: ${answer}`,
  hearSource: "Hear the source",
  nextQuestion: "Next question",
  finishQuiz: "Finish",
  quizScore: (right: number, total: number) => `${right} of ${n(total, "question")} right.`,
  quizResultsCaption: "Your answers",
  quizResultsColQuestion: "Question",
  quizResultsColOutcome: "Answer",
  quizResultRight: "Right",
  quizResultWrong: "Not right",
  hearQuestion: "Hear the question",
  backToQuizzes: "Back to question sets",
  backToQuiz: "Back to the questions",
  correctIs: (answer: string) => `The answer: ${answer}`,
  removeQuestion: (index: number) => `Remove question ${index}`,
  questionRemoved: "Question removed.",
  publishQuiz: "Publish to the class",
  quizPublished: "Questions published to the class.",
  quizReviewIntro:
    "Check each question before students can see it. Remove any that are not suitable; questions cannot be edited.",
  errorNoQuestions: "No questions could be made from this book.",
  prerenderHeading: "Audio for the class",
  prerenderIntro:
    "Turn every sentence of the book into audio ahead of time, so students do not wait when they start listening. Withheld pages are not voiced. If you stop, starting again carries on where it left off.",
  prerenderProgress: (ready: number, total: number) => `${ready} of ${n(total, "sentence")} ready.`,
  prerenderDone: "Every sentence is ready.",
  prerenderAction: "Prepare the audio now",
  prerenderStarted: "Preparing the audio. This can take some time.",
  onlyTeachersShare: "Only teachers can share with classes.",
  errorSignIn: "The email address or password is not right.",
  errorRecover: "The email address and recovery code do not match.",
  errorEmailTaken:
    "There is already an account for this email address. Sign in, or recover the account.",
  errorWeakPassword: (min: number) => `The password must be at least ${n(min, "character")}.`,
  recoveryCodeHeading: "Your recovery code",
  recoveryCodeIntro:
    "This is how you get back into your account if you forget your password. It is not shown again. Copy it, or download it as a file, and keep it somewhere safe.",
  copyCode: "Copy the code",
  codeCopied: "Code copied.",
  downloadCode: "Download as a file",
  savedCodeConfirm: "I have kept this code safe",
  continueToLibrary: "Go to my books",
  recoveryFileName: "swara-recovery-code.txt",
  recoveryFileText: (email: string, code: string) =>
    `Swara recovery code\n\nAccount: ${email}\nCode: ${code}\n\nIf you forget your password, use this on the "Recover your account" page. You will be given a new code after using it.\n`,

  // -- library -----------------------------------------------------------
  libraryHeading: "My books",
  libraryEmpty: "No books yet. Add a book below.",
  uploadHeading: "Add a book",
  uploadLabel: "Choose a PDF file",
  uploadHelp: "Add one or more PDF, Word or image files. Your documents are private.",
  uploadSubmit: "Add",
  uploadInProgress: "Uploading…",
  uploadNoFile: "Choose a file first.",
  addBook: "Add a book",
  currentReading: "Reading now",
  beginReading: "Start reading",
  browseBooks: "My library",
  searchLibrary: "Search books",
  searchLibraryPlaceholder: "Search books",
  uploadIntro: "Add a PDF file and hear it read aloud.",
  uploadDropTitle: "Choose a Sinhala PDF book",
  uploadDropHelp: "Only you can see your file.",
  changeFile: "Change file",
  uploadSelected: "Chosen file",
  preparingBook: "Preparing the book…",
  preparingStepsHeading: "Preparing the book to read",
  preparingStepsIntro: "When this is done you can hear it read aloud.",
  preparingSteps: [
    "Checking the file",
    "Getting the text from each page",
    "Dividing it into sentences",
    "Getting ready for the voice",
  ],
  open: "Open",
  deleteBook: "Delete",
  deleteConfirmTitle: "Delete this book?",
  deleteConfirmBody: (title: string) =>
    `"${title}" and its audio, notes and bookmarks are removed. This cannot be undone.`,
  deleteConfirmCancel: "Cancel",
  deleteConfirmAction: "Delete book",
  deleted: "The book has been deleted.",

  // -- bookmarks ---------------------------------------------------------
  bookmarksNav: "Bookmarks",
  primaryNavigation: "Main navigation",
  publicNavigation: "About Swara",
  footerNavigation: "Site statements",
  howItWorksNav: "How it works",
  forTeachersNav: "For teachers",
  helpNav: "Help",
  accessibilityNav: "Accessibility statement",
  privacyNav: "Privacy",
  termsNav: "Terms of use",
  homeTitle: "A Sinhala study platform",
  lastReviewed: (date: string) => `Last reviewed: ${date}`,
  reportBarrier: "Report a barrier or a problem",
  processingNowHeading: "On this server now",
  processingNowChecking: "Checking the server's settings…",
  processingNowUnknown: "The server's settings cannot be checked right now.",
  processingStructure: "Finding page structure",
  processingAnswers: "Answers to questions",
  processingOcr: "Reading scanned pages",
  processingHere: "On the Swara server itself; nothing leaves it",
  processingGoogle: "Sent to Google Gemini",
  processingGoogleVision: "Sent to Google Cloud Vision",
  processingOff: "Not in use",
  mobileNavigation: "Mobile navigation",
  bookmarksHeading: "Bookmarks",
  bookmarksIntro: "The places you marked to come back to.",
  bookmarksLoading: "Getting bookmarks…",
  bookmarkCurrentSentence: "Bookmark the sentence being read",
  bookmarkSentence: (page: number, sentence: number) =>
    `Bookmark sentence ${sentence} on page ${page}`,
  bookmarkSaved: "Bookmark saved.",
  bookmarkUpdated: "Bookmark updated.",
  bookmarkRemoved: "Bookmark removed.",
  undo: "Undo",
  undoBookmark: "Undo saving the bookmark",
  bookmarksEmptyTitle: "No bookmarks yet",
  bookmarksEmptyBody: "Mark an important page while you read.",
  bookmarkOpen: "Open the bookmarked place",
  bookmarkRemove: "Remove bookmark",
  bookmarkRemoveNamed: (book: string, page: string) => `Remove the bookmark on ${page} in ${book}`,
  bookmarkStale: "The book has been prepared again, so this bookmark may have moved.",
  bookmarkMissing: "This bookmark's sentence is no longer there.",
  bookmarkNoPage: "Page number unknown",

  // -- study -------------------------------------------------------------
  studyBook: "Study with the book",
  studyHeading: "Study with the book",
  studyIntro: "Ask a question. The answer is shown from a passage of the book itself.",
  studyHonesty: "Only the book's words, and where they are, are shown here.",
  questionLabel: "Your question",
  questionPlaceholder: "Ask a question about this book",
  questionRequired: "Type a question.",
  askQuestion: "Ask the question",
  answering: "Finding the answer…",
  answerHeading: "Answer",
  answerFound: "Found an answer and the passage it comes from.",
  sourcesHeading: "Passages",
  openCitation: "Open this passage",
  citationPage: (page: string) => `Page ${page}`,
  citationSection: (section: string) => `Section: ${section}`,
  studyAbstainedHeading: "No answer could be found in this book",
  studyAbstainedBody:
    "No passage in the book supports an answer to this question. Try asking in other words.",

  // -- preparation -------------------------------------------------------
  stateQueued: "Waiting",
  stateRunning: "Preparing the book…",
  stateSucceeded: "Ready to read",
  stateFailed: "Preparing the book failed",
  stateCancelled: "Cancelled",
  preparing: "The book is being prepared. You will be told when it is ready.",
  prepared: "The book is ready to read.",
  stageExtracting: "Reading pages",
  stageRecognising: "Recognising text in images",
  stageStructuring: "Arranging sentences",
  failedStalled: "Preparation stopped before it finished. You can try again.",
  failedRejected:
    "This file cannot be read. It may be damaged or protected by a password. Add another copy.",
  failedOther: "Preparing the book failed. You can try again.",
  bookFailed: (title: string) => `Preparing "${title}" failed.`,
  retrying: "Preparing the book again.",

  // -- reader ------------------------------------------------------------
  backToLibrary: "To my books",
  backToReader: "Back to reading",
  pageWord: "Page",
  printedPage: "Printed page",
  ofPages: (index: number, total: number) => `page ${index} of ${total}`,
  pageCount: (count: number) => n(count, "page"),
  previousPage: "Previous page",
  nextPage: "Next page",
  goToPage: "Go to page",

  // -- contents (chapters) -------------------------------------------------
  contentsHeading: "Contents",
  contentsOpen: "Contents",
  chapterWord: "Chapter",
  contentsNone: "No chapters could be found in this book. Move page by page, or by page number.",
  contentsUnknown: "This book's list of chapters has not been made yet.",
  currentChapter: (number: string | null, title: string) =>
    number ? `${number} / ${title}` : title,
  goToPageSubmit: "Go",
  readingTitle: "Reading a book",
  pageLoading: "Getting the page…",
  sentencesHeading: "Sentences",
  sentenceCount: (count: number) => `${n(count, "sentence")}`,
  showWords: "Show words",
  hideWords: "Hide words",
  sentenceWords: "Words in the sentence",
  wordCount: (count: number) => `${n(count, "word")}`,
  noSentences: "This page has no sentences that can be read.",

  closePanel: "Close",
  citationOpened: "Moved to the quoted sentence.",
  citationUnavailable: "That sentence is no longer on this page.",

  roleHeading: "Heading",
  roleCaption: "Figure caption",
  roleContentsRow: "Contents",
  roleListItem: "List item",
  roleTableCell: "Table cell",
  roleAddress: "Address",
  headingLevel: (level: number) => `Level ${level}`,
  playSentence: "Hear this sentence",

  // -- playback ----------------------------------------------------------
  // "Play", not "Listen": "Listen" is the offline player's, and the assistant's
  // button is "Ask the question", so no two controls share a name.
  play: "Play",
  pause: "Pause",
  stop: "Stop",
  previousSentence: "Previous sentence",
  nextSentence: "Next sentence",
  speed: "Speed",
  loadingAudio: "Preparing the audio…",
  nowReading: (index: number) => `Now playing sentence ${index}.`,
  paused: "Paused.",
  stopped: "Stopped.",
  finishedPage: "End of the page.",
  resumeAvailable: "Your place has been saved.",
  resume: "Carry on from where you stopped",
  resumeStale: "The book has been prepared again, so your place may have moved.",

  // -- honesty about the audio ------------------------------------------
  placeholderAudioHeading: "This is not real speech",
  placeholderAudio:
    "This sound is a demonstration tone. The Sinhala speech model is not connected yet, so it is not reading the book.",
  voiceWarmingHeading: "The voice is warming up",
  voiceWarming:
    "The real Sinhala voice is still loading. This can take over a minute from cold. Nothing will speak until it is ready.",

  // -- what the page loses ----------------------------------------------
  pageNotesHeading: "About this page",
  pageCorrectionHeading: "Correct this page's text",
  pageCorrectionIntro:
    "If OCR or extraction got this page wrong, enter the correct Sinhala text here. Saving creates a new version of the book and regenerates audio for this page.",
  pageCorrectionLabel: "Page text",
  savePageCorrection: "Save corrected text",
  pageCorrected: "The page text was saved.",
  pageCorrectionUnchanged: "The text has not been changed. Correct it before saving.",
  qualityNeedsReview: "Some parts of this page have not been confirmed as read correctly.",
  qualityUndecodable: "This page could not be read. It has not been turned into audio.",
  kindImage: "This page is an image. Its text has not been recognised yet.",
  documentNotesHeading: "About this book",

  // -- failures ----------------------------------------------------------
  errorHeading: "Something went wrong",
  errorOffline: "Cannot reach the server. Check your connection and try again.",
  errorUnreachable: "Swara is starting, or cannot be reached right now. Try again in a moment.",
  errorSignedOut: "You have been signed out. Sign in again.",
  errorForbidden: "This page is out of date. Reload the page and try again.",
  errorThrottled: "Too many attempts. Try again in a little while.",
  errorNotFound: "No such book or page was found.",
  errorNotReady: "The book is not ready yet. Try again in a moment.",
  errorRejected: "This file cannot be accepted.",
  errorUnspeakable: "This sentence has nothing to read.",
  errorServer: "Something unexpected went wrong.",
  retry: "Try again",
  dismiss: "Dismiss",

  // -- shell -------------------------------------------------------------
  skipToContent: "Skip to content",
  footerNote: "Swara — Sinhala books, open to everyone.",

  // -- settings ----------------------------------------------------------
  settingsToggle: "Reading settings",
  settingsHeading: "Reading settings",
  settingsTheme: "Colour scheme",
  themeSystem: "As the device",
  themeLight: "Light",
  themeDark: "Dark",
  settingsTextSize: "Text size",
  settingsTextSizeHelp: "This changes the book's text only.",
  textSizePercent: (scale: number) => `${Math.round(scale * 100)} per cent`,
  settingsReading: "Reading",
  settingFollowSentence: "Follow the sentence being read",
  settingPageTurnSound: "Page-turn sound",
  settingPageTurnSoundHelp: "This can get in the way when you use a screen reader.",
  settingsLanguage: "Interface language",
  settingsLanguageHelp: "Books are always read in their own language.",

  // -- landing -----------------------------------------------------------
  welcomeHeading: "Read and hear Sinhala books",
  welcomeBody:
    "Add a PDF, Word or image file. The original page appears on one side and readable Sinhala text on the other. Choose any sentence and listen.",
  welcomeSecondary: "Only you can see your books.",

  // -- library -----------------------------------------------------------
  continueHeading: "Continue reading",
  continueResume: "Continue reading",
  libraryCount: (count: number) => n(count, "book"),
  coverLoading: "Preparing the cover…",
  filterHeading: "Filter",
  filterAll: "All",
  filterReading: "Reading",
  filterFinished: "Finished",
  filterProcessing: "Being prepared",
  sortHeading: "Order",
  sortRecent: "Last read",
  sortAdded: "Newly added",
  sortTitle: "By name",
  noResultsHeading: "No matching books",
  noResultsBody: (query: string) => `No book was found for "${query}". Try another word.`,
  clearSearch: "Clear the search",
  noneInFilter: "No books match this filter.",
  progressPercent: (percent: number) => `${percent}% read`,
  notStarted: "Not started yet",
  finishedReading: "Finished",
  bookActions: (title: string) => `Actions for ${title}`,
  renameBook: "Rename",
  renameHeading: "Book name",
  renameLabel: "New name",
  renameHelp: "Only you see this name. The original file's name does not change.",
  renameSave: "Save",
  renamed: "Name changed.",
  continueOrOpen: (started: boolean) => (started ? "Continue reading" : "Start reading"),

  // -- upload ------------------------------------------------------------
  uploadDialogHeading: "Add a book",
  uploadDrop: "Drag the file here",
  uploadOr: "or",
  uploadChoose: "Choose a file",
  uploadFormats: "PDF, DOCX, PNG and JPEG — you can choose several files at once.",
  uploadTooBig: "The file is too large.",
  uploadNotPdf: "This is not a PDF file.",
  uploadUnsupported: "Choose PDF, DOCX, PNG or JPEG files only.",
  uploadSelectedCount: (count: number) => `${n(count, "file")} chosen.`,
  uploadSelectedFile: (filename: string) => `Chosen file: ${filename}.`,
  uploadTitleLabel: "Book name (optional)",
  uploadTitleHelp: "If left empty, the file's name is used.",
  uploadTitleSingleOnly: "A name can only be given when one file is chosen.",
  fileSize: (bytes: number) => {
    const mb = bytes / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
  },
  removeFile: "Remove the file",
  removeFiles: "Remove the files",
  uploadFailed: "The upload failed.",

  // -- workspace ---------------------------------------------------------
  originalPanel: "Original page",
  readingPanel: "Reading",
  workspaceTabs: "How to view the page",
  splitLabel: "Width of the two panels",
  splitHelp: "The line between left and right. Change the width with the arrow keys.",
  expandOriginal: "Enlarge the original page",
  expandReading: "Enlarge the reading",
  restoreSplit: "Show both panels",
  restorePanel: (panel: string) => `Show ${panel.toLowerCase()} again`,
  syncPages: "Pages move together",
  syncPagesOff: "Pages move separately",
  zoomIn: "Zoom in on the page",
  zoomOut: "Zoom out of the page",
  fitWidth: "Fit to width",
  zoomLevel: (percent: number) => `Zoom ${percent}%`,
  pdfLoading: "Preparing the original page…",
  pdfFailed: "The original file cannot be shown.",
  originalFailed: "The original file could not be fetched.",
  uploadedImageAlt: (filename: string) => `Uploaded image: ${filename}`,
  docxPreviewUnavailable:
    "The readable text of the Word file is on the right. Download the original file here.",
  downloadOriginal: "Download the original file",
  pdfPageOf: (page: number, total: number) => `Page ${page} of ${total}`,
  thumbnails: "Page thumbnails",
  showThumbnails: "Page list",
  hideThumbnails: "Hide the page list",
  thumbnailGoTo: (page: number) => `Go to page ${page}`,
  returnToSentence: "Back to the sentence being read",
  bookTextSize: "Text size",

  // -- player ------------------------------------------------------------
  playerLabel: "Playback controls",
  playbackPosition: (index: number, total: number) => `Sentence ${index} of ${total}`,
  volume: "Volume",
  audioUnavailable: "This sentence has no audio.",
  buffering: "Preparing the audio…",

  // -- assistant ---------------------------------------------------------
  assistantToggle: "Ask about the book",
  assistantHeading: "Ask about the book",
  assistantResize: "Width of the question panel",
  assistantWidthValue: (percent: number) => `${percent}% of the screen`,
  assistantFor: (book: string) => `About ${book} only`,
  assistantIntro: "Ask a question. The answer is shown from a passage of this book itself.",
  assistantExtractive:
    "These answers are the book's own words. They are not summaries or explanations.",
  assistantGenerated:
    "Answers are written by AI, based on passages of the book. They can be wrong; check the book's passages below.",
  answerFromBook: "From the book",
  answerFromAi: "Written by AI",
  assistantMinimise: "Minimise",
  assistantClear: "Clear the conversation",
  assistantCleared: "Conversation cleared.",
  assistantEmpty: "No questions asked yet.",
  assistantYou: "You",
  assistantAnswer: "From the book",
  assistantAsk: "Ask the question",
  assistantSelectionLabel: "Selected passage",
  assistantSelectionClear: "Clear the selection",
  assistantSuggestions: "Suggestions",
  suggestThisPage: "What is on this page?",
  suggestExplain: "What does the book say about this?",
  conversationLabel: "Questions and answers",

  pipelineNote: (code: string, params: Record<string, string>) => {
    const n = params.name ?? "";
    const family = params.family ?? "";
    const count = params.count ?? "";
    const total = params.total ?? "";
    const withheld = params.withheld ?? "";
    const reason = params.reason ?? "";
    switch (code) {
      case "garbled_native":
        return "The letters on this page could not be extracted correctly. They are not read aloud; the page will be read from its image.";
      case "legacy_unsupported":
        return `The font “${n}” has no validated conversion table. It needs optical recognition or a person to check it.`;
      case "legacy_variant":
        return `The font “${n}” looks like a variant of ${family}. Whether that table applies has not been checked.`;
      case "suspect_encoding":
        return "The extracted characters do not look like Sinhala or ordinary English. They need checking.";
      case "malformed_native":
        return "Some letters here are in an impossible order. They are read aloud, but need checking.";
      case "other_script":
        return "This text is in another script, which this reader has no voice for.";
      case "converted_legacy":
        return `Converted from the legacy font “${n}”. The text was decoded, not proofread.`;
      case "converted_variant":
        return `Converted from the legacy font “${n}”, a variant of ${family}. The text was decoded, not proofread.`;
      case "conversion_failed":
        return `Converting “${n}” produced malformed Sinhala, so it cannot be read aloud.`;
      case "mapping_missing":
        return `The conversion table for “${n}” could not be loaded.`;
      case "unnamed_legacy":
        return `All the text set in “${n}” decodes to nonsense. It is treated as legacy text.`;
      case "suspect_font":
        return `Text set in “${n}” is neither Sinhala nor ordinary English.`;
      case "page_image_only":
        return "This page contains images and no readable text.";
      case "page_mixed_images":
        return `This page contains ${count} image(s) alongside its text. Their content is not described.`;
      case "page_blank":
        return "This page is blank.";
      case "page_columns":
        return "This page looks like it is laid out in columns. The reading order may not match the printed order.";
      case "page_unreadable_lines":
        return `${withheld} of ${total} lines on this page cannot be read yet.`;
      case "page_off_page":
        return `${count} characters drawn outside the printed area were left out.`;
      case "doc_pages_missing":
        return "None of the requested pages exist in this document.";
      case "doc_image_pages":
        return `${count} of ${total} extracted pages are images with no readable text.`;
      case "doc_unreadable_pages":
        return `${count} of ${total} pages have nothing that can be read aloud.`;
      // Older notes said "a teacher"; nothing checked that, so both read alike.
      case "page_corrected":
      case "page_teacher_corrected":
        return "The text on this page was corrected by hand.";
      case "ocr_recognised":
        return "This page was read from its image. Recognition can misread letters, and a person has not checked it.";
      case "ocr_failed":
        return `${count} page(s) could not be read from their image (${reason}) and keep their embedded text.`;
      default:
        return n ? `${code}: ${n}` : code;
    }
  },

  // -- language ----------------------------------------------------------
  draftTranslation:
    "This English page is a draft translation, awaiting review. Where it differs from the Sinhala page, the Sinhala applies.",
};
