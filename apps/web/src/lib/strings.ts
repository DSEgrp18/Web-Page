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
  // Swara — "voice" / "tone". The brand mark is an open book with a gold
  // ribbon; `apps/web/public/brand/` holds the artwork it is cut from.
  appName: "ස්වර",
  appNameLatin: "Swara",
  appTagline: "සිංහල පොත් කියවන්න, අසන්න, තේරුම් ගන්න",

  // -- identity ----------------------------------------------------------
  identityHeading: "ඔබ කවුද?",
  identityLabel: "කියවන්නාගේ නම",
  identityHelp:
    "මෙය තාවකාලික සංවර්ධන ක්‍රමයකි. සැබෑ පිවිසුම් ක්‍රමයක් තවම සකසා නැත; ඔබගේ ලේඛන පෞද්ගලික බව මෙයින් සහතික නොවේ.",
  identitySave: "ඉදිරියට",
  identityChange: "කියවන්නා වෙනස් කරන්න",

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
  preparingStepsHeading: "පොත කියවීමට සූදානම් කරමින්",
  preparingStepsIntro: "මෙය අවසන් වූ විට ඔබට මෙය ශබ්දයෙන් කියවිය හැක.",
  preparingSteps: [
    "ගොනුව පරීක්ෂා කිරීම",
    "පිටු වල අකුරු සකස් කිරීම",
    "වාක්‍ය ලෙස බෙදීම",
    "හඬට සූදානම් කිරීම",
  ],
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

  // -- study -------------------------------------------------------------
  studyBook: "පොත සමඟ අධ්‍යයනය කරන්න",
  studyHeading: "පොත සමඟ අධ්‍යයනය කරන්න",
  studyIntro: "ප්‍රශ්නයක් අසන්න. පිළිතුර පොතේම ඇති කොටසකින් පෙන්වයි.",
  studyHonesty: "මෙහි පෙන්වන්නේ පොතේ වචන සහ ඒවා ඇති තැන් පමණි.",
  questionLabel: "ඔබේ ප්‍රශ්නය",
  questionPlaceholder: "මෙම පොත ගැන ප්‍රශ්නයක් අසන්න",
  questionRequired: "ප්‍රශ්නයක් ඇතුළත් කරන්න.",
  askQuestion: "ප්‍රශ්නය අසන්න",
  answering: "පිළිතුර සොයමින්…",
  answerHeading: "පිළිතුර",
  answerFound: "පිළිතුර සහ එයට අදාළ කොටස හමු විය.",
  sourcesHeading: "අදාළ කොටස්",
  openCitation: "මෙම කොටස විවෘත කරන්න",
  citationPage: (page: string) => `පිටුව ${page}`,
  citationSection: (section: string) => `කොටස: ${section}`,
  studyAbstainedHeading: "මෙම පොතෙන් පිළිතුරක් සොයාගත නොහැක",
  studyAbstainedBody: "මෙම ප්‍රශ්නයට සහය දෙන කොටසක් පොතේ හමු නොවීය. වෙනත් වචන වලින් අසන්න.",

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
  backToReader: "කියවීමට ආපසු යන්න",
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

  // What kind of thing a sentence belongs to. These are announced, not just
  // shown: somebody listening cannot see that a caption has interrupted a
  // paragraph, which is the defect the structure work exists to fix.
  //
  // Only the roles that change what a reader should expect are named. A
  // paragraph is not announced, because announcing "paragraph" before every
  // sentence of a book is noise, and unknown is not announced either, because
  // it reads exactly as prose.
  closePanel: "වසන්න",
  /** Said after a citation moves the reader, because the move is not visible. */
  citationOpened: "උපුටා ගත් වාක්‍යයට ගෙන යන ලදි.",
  /** A citation into text that has since changed. Saying nothing looks broken. */
  citationUnavailable: "එම වාක්‍යය මෙම පිටුවේ තවදුරටත් නැත.",

  roleHeading: "මාතෘකාව",
  roleCaption: "රූප සටහන් විස්තරය",
  roleContentsRow: "පටුන",
  roleListItem: "ලැයිස්තු අයිතමය",
  roleTableCell: "වගු කොටුව",
  roleAddress: "ලිපිනය",
  /** Spoken before a heading, so its depth is audible: "මට්ටම 2 මාතෘකාව". */
  headingLevel: (level: number) => `මට්ටම ${level}`,
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

  // -- shell -------------------------------------------------------------
  skipToContent: "අන්තර්ගතයට යන්න",
  footerNote: "ස්වර — සිංහල පොත් සියලු දෙනාටම විවෘතයි.",

  // -- settings ----------------------------------------------------------
  settingsToggle: "කියවීමේ සැකසුම්",
  settingsHeading: "කියවීමේ සැකසුම්",
  settingsTheme: "වර්ණ රටාව",
  themeSystem: "උපාංගය අනුව",
  themeLight: "ආලෝකමත්",
  themeDark: "අඳුරු",
  settingsTextSize: "අකුරු ප්‍රමාණය",
  settingsTextSizeHelp: "මෙය පොතේ අකුරු පමණක් වෙනස් කරයි.",
  textSizePercent: (scale: number) => `සියයට ${Math.round(scale * 100)}`,
  settingsReading: "කියවීම",
  settingFollowSentence: "කියවන වාක්‍යය අනුව ගමන් කරන්න",
  settingPageTurnSound: "පිටුව හැරවීමේ ශබ්දය",
  settingPageTurnSoundHelp: "තිර කියවනයක් භාවිත කරන විට මෙය ඔබට බාධා විය හැක.",

  // -- landing -----------------------------------------------------------
  welcomeHeading: "සිංහල පොත් කියවන්න, අසන්න",
  welcomeBody:
    "PDF පොතක් එක් කරන්න. මුල් පිටුව එක් පසෙකත්, කියවිය හැකි සිංහල අකුර අනෙක් පසෙකත් පෙනේ. ඕනෑම වාක්‍යයක් තෝරා ඇහුම්කන් දෙන්න.",
  welcomeSecondary: "ඔබේ පොත් ඔබට පමණක් පෙනේ.",

  // -- library -----------------------------------------------------------
  continueHeading: "දිගටම කියවන්න",
  continueResume: "දිගටම කියවන්න",
  libraryCount: (count: number) => `පොත් ${count} ක්`,
  coverLoading: "කවරය සකසමින්…",
  filterHeading: "පෙරහන",
  filterAll: "සියල්ල",
  filterReading: "කියවමින්",
  filterFinished: "අවසන් කළ",
  filterProcessing: "සූදානම් වෙමින්",
  sortHeading: "පිළිවෙල",
  sortRecent: "අවසන් කියවූ",
  sortAdded: "අලුතින් එක් කළ",
  sortTitle: "නම අනුව",
  noResultsHeading: "ගැළපෙන පොතක් නැත",
  noResultsBody: (query: string) => `"${query}" සඳහා පොතක් හමු නොවීය. වෙනත් වචනයක් උත්සාහ කරන්න.`,
  clearSearch: "සෙවීම හිස් කරන්න",
  noneInFilter: "මෙම පෙරහනට ගැළපෙන පොත් නැත.",
  progressPercent: (percent: number) => `සියයට ${percent} ක් කියවා ඇත`,
  notStarted: "තවම ආරම්භ කර නැත",
  finishedReading: "අවසන් කර ඇත",
  bookActions: (title: string) => `${title} සඳහා ක්‍රියා`,
  renameBook: "නම වෙනස් කරන්න",
  renameHeading: "පොතේ නම",
  renameLabel: "නව නම",
  renameHelp: "මෙය ඔබට පමණක් පෙනෙන නමකි. මුල් ගොනුවේ නම වෙනස් නොවේ.",
  renameSave: "සුරකින්න",
  renamed: "නම වෙනස් කරන ලදි.",
  continueOrOpen: (started: boolean) => (started ? "දිගටම කියවන්න" : "කියවීම අරඹන්න"),

  // -- upload ------------------------------------------------------------
  uploadDialogHeading: "පොතක් එක් කරන්න",
  uploadDrop: "ගොනුව මෙහි අදින්න",
  uploadOr: "නැතහොත්",
  uploadChoose: "ගොනුවක් තෝරන්න",
  uploadOnlyPdf: "PDF ගොනු පමණි.",
  uploadTooBig: "ගොනුව විශාල වැඩියි.",
  uploadNotPdf: "මෙය PDF ගොනුවක් නොවේ.",
  uploadTitleLabel: "පොතේ නම (අත්‍යවශ්‍ය නොවේ)",
  uploadTitleHelp: "හිස් තැබුවහොත් ගොනුවේ නම භාවිත වේ.",
  fileSize: (bytes: number) => {
    const mb = bytes / (1024 * 1024);
    return mb >= 1
      ? `මෙගාබයිට් ${mb.toFixed(1)}`
      : `කිලෝබයිට් ${Math.max(1, Math.round(bytes / 1024))}`;
  },
  removeFile: "ගොනුව ඉවත් කරන්න",
  uploadFailed: "උඩුගත කිරීම අසාර්ථක විය.",

  // -- workspace ---------------------------------------------------------
  originalPanel: "මුල් පිටුව",
  readingPanel: "කියවීම",
  workspaceTabs: "පිටුව බැලීමේ ක්‍රමය",
  splitLabel: "පැනල දෙකේ පළල",
  splitHelp: "වම හා දකුණ බෙදන රේඛාව. ඊතල යතුරු වලින් පළල වෙනස් කරන්න.",
  expandOriginal: "මුල් පිටුව විශාල කරන්න",
  expandReading: "කියවීම විශාල කරන්න",
  restoreSplit: "පැනල දෙකම පෙන්වන්න",
  syncPages: "පිටු එකට ගමන් කරයි",
  syncPagesOff: "පිටු වෙන් වෙන්ව ගමන් කරයි",
  zoomIn: "පිටුව විශාල කරන්න",
  zoomOut: "පිටුව කුඩා කරන්න",
  fitWidth: "පළලට ගළපන්න",
  zoomLevel: (percent: number) => `විශාලනය සියයට ${percent}`,
  pdfLoading: "මුල් පිටුව සකසමින්…",
  pdfFailed: "මුල් ගොනුව පෙන්විය නොහැක.",
  pdfPageOf: (page: number, total: number) => `පිටු ${total} න් ${page}`,
  thumbnails: "පිටු කුඩා රූප",
  showThumbnails: "පිටු ලැයිස්තුව",
  hideThumbnails: "පිටු ලැයිස්තුව සඟවන්න",
  thumbnailGoTo: (page: number) => `පිටුව ${page} ට යන්න`,
  returnToSentence: "කියවන වාක්‍යයට ආපසු",
  bookTextSize: "අකුරු ප්‍රමාණය",

  // -- player ------------------------------------------------------------
  playerLabel: "ශබ්ද පාලනය",
  playbackPosition: (index: number, total: number) => `වාක්‍ය ${total} න් ${index}`,
  volume: "හඬ ප්‍රමාණය",
  audioUnavailable: "මෙම වාක්‍යයට ශබ්දයක් නැත.",
  buffering: "ශබ්දය සකසමින්…",

  // -- assistant ---------------------------------------------------------
  assistantToggle: "පොත ගැන අසන්න",
  assistantHeading: "පොත ගැන අසන්න",
  assistantFor: (book: string) => `${book} ගැන පමණි`,
  assistantIntro: "ප්‍රශ්නයක් අසන්න. පිළිතුර මෙම පොතේම ඇති කොටසකින් පෙන්වයි.",
  /** Said when the answerer returns the book's own sentences. */
  assistantExtractive: "මෙම පිළිතුරු පොතේ වචන ම වේ. ඒවා සාරාංශ හෝ පැහැදිලි කිරීම් නොවේ.",
  /** Said when a model wrote the answer. A reader cannot see which they got. */
  assistantGenerated:
    "පිළිතුරු ලියන්නේ AI විසිනි, පොතේ කොටස් මත පදනම්ව. ඒවා වැරදි විය හැක; පහත පොතේ කොටස් පරීක්ෂා කරන්න.",
  answerFromBook: "පොතෙන්",
  answerFromAi: "AI විසින් ලියන ලදි",
  assistantMinimise: "කුඩා කරන්න",
  assistantClear: "සංවාදය හිස් කරන්න",
  assistantCleared: "සංවාදය හිස් කරන ලදි.",
  assistantEmpty: "තවම ප්‍රශ්න අසා නැත.",
  assistantYou: "ඔබ",
  assistantAnswer: "පොතෙන්",
  // Not plain "අසන්න": that is the play button's name, and two buttons with
  // the same accessible name doing different things is exactly what a screen
  // reader cannot disambiguate.
  assistantAsk: "ප්‍රශ්නය අසන්න",
  assistantSelectionLabel: "තෝරාගත් කොටස",
  assistantSelectionClear: "තේරීම ඉවත් කරන්න",
  assistantSuggestions: "යෝජනා",
  suggestThisPage: "මෙම පිටුවේ ඇත්තේ කුමක්ද?",
  suggestExplain: "මෙය ගැන පොතේ කියන්නේ කුමක්ද?",
  conversationLabel: "ප්‍රශ්න හා පිළිතුරු",
} as const;

/** What each theme choice is called. A switch, so a new theme cannot be missed. */
export function themeName(theme: "system" | "light" | "dark"): string {
  switch (theme) {
    case "light":
      return strings.themeLight;
    case "dark":
      return strings.themeDark;
    default:
      return strings.themeSystem;
  }
}

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
