/**
 * Every word the interface says, in one place, in Sinhala.
 *
 * CLAUDE.md makes Sinhala the primary UI language and requires controls,
 * errors, and status messages to be reviewed by a native speaker. Keeping them
 * in one module is what makes that review a single readable file rather than a
 * hunt through components.
 *
 * ⚠️ **These translations have NOT been reviewed by a native speaker yet.**
 * That review is a release requirement, not a nicety: a screen-reader user hears
 * these strings and nothing else, so an awkward or wrong word is the whole
 * interface. See `apps/web/README.md`.
 *
 * A note on what is *not* here: text that comes from the API — page notes,
 * failure details — is already Sinhala-facing prose written by the server, and
 * is shown as received. Translating it twice would be two places to get it wrong.
 */

export const strings = {
  // Penpot product name — Handa Potha, "voice book".
  appName: "හඬ පොත",
  appTagline: "අකුරු හඬට හැරෙන තැන",

  // -- identity ----------------------------------------------------------
  identityHeading: "ඔබ කවුද?",
  identityLabel: "කියවන්නාගේ නම",
  identityHelp:
    "මෙය තාවකාලික සංවර්ධන ක්‍රමයකි. සැබෑ පිවිසුම් ක්‍රමයක් තවම සකසා නැත; ඔබගේ ලේඛන පෞද්ගලික බව මෙයින් සහතික නොවේ.",
  identitySave: "ඉදිරියට",
  identityChange: "නම වෙනස් කරන්න",

  // -- library -----------------------------------------------------------
  libraryHeading: "මගේ පොත්",
  libraryEmpty: "තවම පොත් නැත. පහතින් පොතක් එක් කරන්න.",
  uploadHeading: "පොතක් එක් කරන්න",
  uploadLabel: "PDF ගොනුවක් තෝරන්න",
  uploadHelp: "සිංහල PDF ලේඛන පමණි. ඔබගේ ලේඛන පෞද්ගලිකයි.",
  uploadSubmit: "එක් කරන්න",
  uploadInProgress: "උඩුගත වෙමින්…",
  uploadNoFile: "පළමුව ගොනුවක් තෝරන්න.",
  addBook: "පොතක් එක් කරන්න",
  currentReading: "කියවමින් සිටින්නෙහි",
  beginReading: "කියවීම අරඹන්න",
  browseBooks: "මගේ පොත් එකතුව",
  searchLibrary: "පොත් සොයන්න",
  searchLibraryPlaceholder: "පොත් සොයන්න",
  uploadIntro: "PDF ගොනුවක් එක් කර එය ශබ්දයෙන් කියවන්න.",
  uploadDropTitle: "සිංහල PDF පොතක් තෝරන්න",
  uploadDropHelp: "ඔබේ ගොනුව ඔබට පමණක් පෙනේ.",
  changeFile: "ගොනුව වෙනස් කරන්න",
  uploadSelected: "තෝරාගත් ගොනුව",
  preparingBook: "පොත සූදානම් කරමින්…",
  open: "විවෘත කරන්න",
  deleteBook: "මකන්න",
  // Penpot → Dialog · delete book
  deleteConfirmTitle: "මෙම පොත මකන්න ද?",
  deleteConfirmBody: (title: string) =>
    `"${title}" සහ එයට අදාළ හඬ, සටහන් හා පිටු සලකුණු ඉවත් වේ. මෙම ක්‍රියාව ආපසු හැරවිය නොහැක.`,
  deleteConfirmCancel: "අවලංගු කරන්න",
  deleteConfirmAction: "පොත මකන්න",
  deleted: "පොත මකා දමන ලදී.",

  // -- bookmarks ---------------------------------------------------------
  bookmarksNav: "පිටු සලකුණු",
  primaryNavigation: "ප්‍රධාන සංචාලනය",
  mobileNavigation: "ජංගම සංචාලනය",
  bookmarksHeading: "පිටු සලකුණු",
  bookmarksIntro: "ඔබ නැවත එන්නට සලකුණු කළ තැන්.",
  bookmarksLoading: "පිටු සලකුණු ලබා ගනිමින්…",
  bookmarkCurrentSentence: "කියවන වාක්‍යය සලකුණු කරන්න",
  bookmarkSentence: (page: number, sentence: number) =>
    `පිටුව ${page} හි ${sentence} වැනි වාක්‍යය සලකුණු කරන්න`,
  bookmarkSaved: "පිටු සලකුණ සුරැකිණි.",
  bookmarkUpdated: "පිටු සලකුණ යාවත්කාලීන කරන ලදි.",
  bookmarkRemoved: "පිටු සලකුණ ඉවත් කරන ලදි.",
  undo: "ආපසු හරවන්න",
  undoBookmark: "පිටු සලකුණ සුරැකීම ආපසු හරවන්න",
  bookmarksEmptyTitle: "තවමත් සලකුණු නැත",
  bookmarksEmptyBody: "කියවන අතරතුර වැදගත් පිටුවක් සලකුණු කරන්න.",
  bookmarkOpen: "සලකුණු කළ තැන විවෘත කරන්න",
  bookmarkRemove: "පිටු සලකුණ ඉවත් කරන්න",
  bookmarkRemoveNamed: (book: string, page: string) => `${book} හි ${page} පිටු සලකුණ ඉවත් කරන්න`,
  bookmarkStale: "පොත නැවත සකසා ඇති නිසා මෙම සලකුණ වෙනස් විය හැක.",
  bookmarkMissing: "මෙම සලකුණේ වාක්‍යය තවදුරටත් නොමැත.",
  bookmarkNoPage: "පිටු අංකය නොදනී",

  // -- preparation -------------------------------------------------------
  stateQueued: "පෝලිමේ",
  stateRunning: "පොත සූදානම් වෙමින්…",
  stateSucceeded: "කියවීමට සූදානම්",
  stateFailed: "සූදානම් කිරීම අසාර්ථක විය",
  stateCancelled: "අවලංගු කරන ලදී",
  preparing: "පොත සූදානම් වෙමින් පවතී. සූදානම් වූ පසු දැනුම් දෙනු ලැබේ.",
  prepared: "පොත කියවීමට සූදානම්.",

  // -- reader ------------------------------------------------------------
  backToLibrary: "පොත් ලැයිස්තුවට",
  pageWord: "පිටුව",
  printedPage: "මුද්‍රිත පිටුව",
  ofPages: (index: number, total: number) => `පිටු ${total} න් ${index}`,
  pageCount: (count: number) => `පිටු ${count} ක්`,
  previousPage: "පෙර පිටුව",
  nextPage: "ඊළඟ පිටුව",
  goToPage: "පිටුවට යන්න",
  goToPageSubmit: "යන්න",
  pageLoading: "පිටුව ලබා ගනිමින්…",
  sentencesHeading: "වාක්‍ය",
  sentenceCount: (count: number) => `වාක්‍ය ${count} ක්`,
  noSentences: "මෙම පිටුවේ කියවිය හැකි වාක්‍ය නැත.",
  playSentence: "මෙම වාක්‍යය අසන්න",

  // -- playback ----------------------------------------------------------
  play: "අසන්න",
  pause: "විරාම කරන්න",
  stop: "නවත්වන්න",
  previousSentence: "පෙර වාක්‍යය",
  nextSentence: "ඊළඟ වාක්‍යය",
  speed: "වේගය",
  loadingAudio: "ශබ්දය සකසමින්…",
  nowReading: (index: number) => `දැන් අසන්නේ ${index} වන වාක්‍යයයි.`,
  paused: "විරාම කර ඇත.",
  stopped: "නවත්වන ලදී.",
  finishedPage: "පිටුව අවසන්.",
  resumeAvailable: "ඔබ නැවතුණු තැන සුරැකී ඇත.",
  resume: "නැවතුණු තැනින් ඉදිරියට",
  resumeStale: "පොත නැවත සකසා ඇති නිසා, ඔබ නැවතුණු තැන වෙනස් වී තිබිය හැක.",

  // -- honesty about the audio ------------------------------------------
  placeholderAudioHeading: "මෙය සැබෑ කථනයක් නොවේ",
  placeholderAudio:
    "මෙම ශබ්දය ආදර්ශන ස්වරයකි. සිංහල කථන ආකෘතිය තවම සම්බන්ධ කර නැති නිසා, මෙය පොතේ අන්තර්ගතය කියවන්නේ නැත.",

  // -- what the page loses ----------------------------------------------
  pageNotesHeading: "මෙම පිටුව ගැන",
  qualityNeedsReview: "මෙම පිටුවේ සමහර කොටස් නිවැරදිව කියවා ඇත්දැයි තහවුරු කර නැත.",
  qualityUndecodable: "මෙම පිටුව කියවිය නොහැකි විය. එය ශබ්දයට හරවා නැත.",
  kindImage: "මෙම පිටුව රූපයකි. එහි අකුරු තවම හඳුනාගෙන නැත.",
  documentNotesHeading: "මෙම පොත ගැන",

  // -- failures ----------------------------------------------------------
  errorHeading: "දෝෂයක්",
  errorOffline: "සේවාදායකයට සම්බන්ධ විය නොහැක. සම්බන්ධතාවය පරීක්ෂා කර නැවත උත්සාහ කරන්න.",
  errorIdentity: "ඔබව හඳුනාගත නොහැක. නම නැවත ඇතුළත් කරන්න.",
  errorNotFound: "එවැනි පොතක් හෝ පිටුවක් හමු නොවීය.",
  errorNotReady: "පොත තවම සූදානම් නැත. මොහොතකින් නැවත උත්සාහ කරන්න.",
  errorRejected: "මෙම ගොනුව පිළිගත නොහැක.",
  errorUnspeakable: "මෙම වාක්‍යයේ කියවීමට යමක් නැත.",
  errorServer: "අනපේක්ෂිත දෝෂයක් සිදු විය.",
  retry: "නැවත උත්සාහ කරන්න",
  dismiss: "ඉවත් කරන්න",
} as const;

/** The one message a reader hears for each way a request can fail. */
export function messageFor(kind: string): string {
  switch (kind) {
    case "offline":
      return strings.errorOffline;
    case "identity":
      return strings.errorIdentity;
    case "not_found":
      return strings.errorNotFound;
    case "not_ready":
      return strings.errorNotReady;
    case "rejected":
      return strings.errorRejected;
    case "unspeakable":
      return strings.errorUnspeakable;
    default:
      return strings.errorServer;
  }
}

export function jobStateMessage(state: string): string {
  switch (state) {
    case "queued":
      return strings.stateQueued;
    case "running":
      return strings.stateRunning;
    case "succeeded":
      return strings.stateSucceeded;
    case "failed":
      return strings.stateFailed;
    case "cancelled":
      return strings.stateCancelled;
    default:
      return state;
  }
}
