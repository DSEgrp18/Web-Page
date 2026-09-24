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
 * A note on what is *not* here: page notes from the API are already
 * Sinhala-facing prose written by the server, and are shown as received.
 * Translating them twice would be two places to get it wrong. A job's failure
 * `detail` is different: it is an English diagnostic, so a failed book is
 * described from its stage instead (`jobFailureMessage`).
 */

import type { Job } from "./types";

export const strings = {
  // Swara — "voice" / "tone". The brand mark is an open book with a gold
  // ribbon; `apps/web/public/brand/` holds the artwork it is cut from.
  appName: "ස්වර",
  appNameLatin: "Swara",
  appTagline: "සිංහල පොත් කියවන්න, අසන්න, තේරුම් ගන්න",

  // -- account -----------------------------------------------------------
  signInHeading: "ඇතුළු වන්න",
  signInAction: "ඇතුළු වන්න",
  registerHeading: "ගිණුමක් සාදන්න",
  registerAction: "ගිණුම සාදන්න",
  recoverHeading: "ගිණුම නැවත ලබා ගන්න",
  recoverIntro:
    "ගිණුම සාදන විට ඔබට ලැබුණු ප්‍රතිසාධන කේතයෙන් නව මුරපදයක් සකසන්න. ඊමේල් පණිවිඩයක් අවශ්‍ය නැත.",
  recoverAction: "නව මුරපදය සකසන්න",
  emailLabel: "ඊමේල් ලිපිනය",
  passwordLabel: "මුරපදය",
  newPasswordLabel: "නව මුරපදය",
  passwordHint: (min: number) => `අවම වශයෙන් අකුරු ${min} ක්.`,
  showPassword: "මුරපදය පෙන්වන්න",
  displayNameLabel: "ඔබේ නම",
  displayNameHint: "ස්වර ඔබට ආමන්ත්‍රණය කරන නම.",
  recoveryCodeLabel: "ප්‍රතිසාධන කේතය",
  recoveryCodeHint:
    "අකුරු අතර ඉඩ හෝ ඉරි තිබුණත් කමක් නැත. කැපිටල් හෝ සිම්පල් අකුරු දෙකම පිළිගනී. ගුරුවරයා දුන් කේතයක් ද මෙහි ලියන්න.",
  signedOutHeading: "ඔබේ පොත් කියවීමට ඇතුළු වන්න",
  signedOutBody: "ඔබේ පොත් ඔබට පමණක් පෙනේ. ඒවා විවෘත කිරීමට ඔබේ ගිණුමෙන් ඇතුළු වන්න.",
  noAccountYet: "ගිණුමක් නැද්ද?",
  haveAccount: "දැනටමත් ගිණුමක් තිබේද?",
  forgotPassword: "මුරපදය අමතකද?",
  signOut: "පිටවන්න",
  signedOut: "ඔබ පිටව ගියා.",
  signedIn: "ඔබ ඇතුළු වුණා.",
  loadingSession: "පූරණය වෙමින්…",
  // The account page.
  accountHeading: "මගේ ගිණුම",
  accountDetails: "ගිණුමේ විස්තර",
  roleTerm: "භූමිකාව",
  roleName: (role: string) =>
    role === "teacher" ? "ගුරු" : role === "admin" ? "පරිපාලක" : "ශිෂ්‍ය",
  currentPasswordLabel: "වත්මන් මුරපදය",
  changePasswordHeading: "මුරපදය වෙනස් කරන්න",
  changePasswordAction: "මුරපදය වෙනස් කරන්න",
  passwordChanged: "මුරපදය වෙනස් කළා. වෙනත් උපාංගවල ඔබ පිටවී ඇත.",
  errorWrongPassword: "වත්මන් මුරපදය නිවැරදි නැත.",
  recoveryHeading: "ප්‍රතිසාධන කේතය",
  recoveryMissing:
    "ඔබේ ගිණුමට ප්‍රතිසාධන කේතයක් නැත. මුරපදය අමතක වුවහොත් නැවත පිවිසීමට එකක් සාදන්න.",
  recoveryReplaceIntro: "නව කේතයක් සෑදූ විට පැරණි කේතය තවදුරටත් ක්‍රියා නොකරයි.",
  newRecoveryAction: "නව ප්‍රතිසාධන කේතයක් සාදන්න",
  backToAccount: "මගේ ගිණුමට ආපසු",
  everywhereHeading: "සියලු උපාංගවලින් පිටවන්න",
  everywhereIntro: "හවුලේ හෝ නැති වූ දුරකථනයක ඔබ ඇතුළු වී සිටියේ නම්, මෙයින් එහිද මෙහිද ඔබ පිටවේ.",
  everywhereAction: "සියලු උපාංගවලින් පිටවන්න",
  signedOutEverywhere: "ඔබ සියලු උපාංගවලින් පිටව ගියා.",
  deleteAccountHeading: "ගිණුම මකන්න",
  deleteAccountIntro:
    "ඔබේ ගිණුම සහ ඔබේ සියලු පොත්, හඬ, සටහන් හා පිටු සලකුණු ඉවත් වේ. මෙය ආපසු හැරවිය නොහැක.",
  deleteAccountAction: "ගිණුම මකන්න",
  deleteAccountConfirmTitle: "ඔබේ ගිණුම මකන්න ද?",
  deleteAccountConfirmBody:
    "ඔබේ සියලු පොත් සහ ඒවායින් සැකසූ සියල්ල සදහටම ඉවත් වේ. මෙය ආපසු හැරවිය නොහැක.",
  accountDeleted: "ඔබේ ගිණුම මකා දැමුණා.",
  // -- classes -------------------------------------------------------------
  classesNav: "පන්ති",
  classesHeading: "මගේ පන්ති",
  joinHeading: "පන්තියකට එක් වන්න",
  joinCodeLabel: "පන්ති කේතය",
  joinCodeHint: "ගුරුවරයා දුන් ඉලක්කම් අටේ කේතය. ඉඩ හෝ ඉරි තිබුණත් කමක් නැත.",
  shareProgressLabel: "මගේ ප්‍රගතිය ගුරුවරයාට පෙන්වන්න",
  shareProgressHint:
    "පෙරනිමියෙන් නිවා ඇත. ඕනෑම වේලාවක වෙනස් කළ හැක. ඔබේ පොත්, සටහන් හෝ ප්‍රශ්න කිසි විටෙක නොපෙනේ.",
  joinAction: "එක් වන්න",
  joinedWaiting: (name: string) =>
    `"${name}" පන්තියට ඉල්ලීම යැව්වා. ගුරුවරයා අනුමත කළ පසු පන්තියේ පොත් පෙනේ.`,
  errorNoClassCode: "එම කේතය සහිත පන්තියක් නැත. කේතය නැවත පරීක්ෂා කරන්න.",
  joinedHeading: "ඔබ සිටින පන්ති",
  noJoined: "ඔබ තවම කිසිම පන්තියක නැත.",
  memberState: (state: string) =>
    state === "active" ? "සාමාජික" : state === "removed" ? "ඉවත් කළා" : "අනුමැතිය බලාපොරොත්තුවෙන්",
  teacherOf: (name: string) => `ගුරුවරයා: ${name}`,
  progressShared: "ප්‍රගතිය ගුරුවරයාට පෙන්වයි.",
  progressPrivate: "ප්‍රගතිය ඔබට පමණයි.",
  leaveClass: "පන්තියෙන් ඉවත් වන්න",
  leftClass: "ඔබ පන්තියෙන් ඉවත් වුණා.",
  teachingHeading: "ඔබ උගන්වන පන්ති",
  createClassLabel: "නව පන්තියේ නම",
  createClassAction: "පන්තිය සාදන්න",
  classCreated: "පන්තිය සෑදුවා.",
  noTaught: "ඔබ තවම පන්ති සාදා නැත.",
  memberCounts: (active: number, pending: number) =>
    `සිසුන් ${active}ක්, අනුමැතිය බලාපොරොත්තුවෙන් ${pending}ක්`,
  classCodeHeading: "පන්ති කේතය",
  classCodeHint: "මෙම කේතය ඔබේ සිසුන්ට දෙන්න. ඔබ අනුමත කරන තුරු ඔවුන්ට පන්තියේ පොත් නොපෙනේ.",
  newCodeAction: "නව කේතයක් සාදන්න",
  newCodeDone: "නව කේතය සෑදුවා. පැරණි කේතය තවදුරටත් ක්‍රියා නොකරයි.",
  membersHeading: "සිසුන්",
  noMembers: "තවම කිසිවෙක් එක් වී නැත.",
  memberColName: "නම",
  memberColState: "තත්ත්වය",
  memberColShares: "ප්‍රගතිය පෙන්වයි",
  memberColActions: "ක්‍රියා",
  yes: "ඔව්",
  no: "නැත",
  approveNamed: (name: string) => `${name} අනුමත කරන්න`,
  removeNamed: (name: string) => `${name} ඉවත් කරන්න`,
  memberApproved: (name: string) => `${name} අනුමත කළා.`,
  memberRemoved: (name: string) => `${name} ඉවත් කළා.`,
  // A reset code, made by the teacher for a student who lost their password
  // and their own recovery code.
  resetNamed: (name: string) => `${name} සඳහා මුරපදය නැවත සැකසීමේ කේතයක්`,
  resetConfirmTitle: (name: string) => `${name} සඳහා මුරපදය නැවත සැකසීමේ කේතයක් සාදන්න ද?`,
  resetConfirmBody:
    'කේතය එක් වරක් පමණක්, විනාඩි 30ක් ඇතුළත ක්‍රියා කරයි. ඔවුන්ගේම ප්‍රතිසාධන කේතය තවමත් ක්‍රියා කරයි. ඔවුන් මෙම කේතය සහ ඔවුන්ගේම ඊමේල් ලිපිනය "ගිණුම නැවත ලබා ගන්න" පිටුවේ භාවිත කරන තුරු මුරපදය වෙනස් නොවේ. ඔබ කේතය සෑදූ බව ඔවුන්ට දැනුම් දෙනු ලැබේ.',
  resetConfirmAction: "කේතය සාදන්න",
  resetCodeHeading: (name: string) => `${name} සඳහා කේතය`,
  resetCodeIntro:
    'මෙය ඔවුන්ට පෞද්ගලිකව දෙන්න. මෙය නැවත පෙන්වන්නේ නැත, සහ විනාඩි 30කින් කල් ඉකුත් වේ. ඔවුන් "ගිණුම නැවත ලබා ගන්න" පිටුවේ මෙය ඔවුන්ගේම ඊමේල් ලිපිනය සමඟ භාවිත කරයි.',
  resetIssued: (name: string) => `${name} සඳහා කේතයක් සෑදුවා.`,
  resetDone: "අවසන්",
  // What the student is told, on every screen, until they say they have seen it.
  resetNoticeHeading: "ඔබේ ගිණුම ගැන දැනුම්දීමක්",
  resetNoticeText: (teacher: string | null, when: string, used: boolean) =>
    `${teacher ? `${teacher} ගුරුවරයා` : "ඔබේ ගුරුවරයෙක්"} ${when} ඔබේ ගිණුම සඳහා මුරපදය නැවත සැකසීමේ කේතයක් සෑදුවා. ` +
    (used ? "එම කේතයෙන් මුරපදය වෙනස් කර ඇත. " : "එය තවම භාවිත කර නැත. ") +
    "ඔබ එය ඉල්ලුවේ නැත්නම්, ඔබේ ගුරුවරයාට හෝ සේවා කණ්ඩායමට කියන්න.",
  resetNoticeSeen: "තේරුණා",
  renameClassLabel: "පන්තියේ නම",
  renameClassAction: "නම සුරකින්න",
  classRenamed: "පන්තියේ නම වෙනස් කළා.",
  deleteClassAction: "පන්තිය මකන්න",
  deleteClassConfirmTitle: "මෙම පන්තිය මකන්න ද?",
  deleteClassConfirmBody:
    "සියලු සිසුන් පන්තියෙන් ඉවත් වන අතර පන්තිය සමඟ බෙදා ගත් පොත් ඔවුන්ට තවදුරටත් නොපෙනේ. ඔවුන්ගේම පොත්වලට බලපෑමක් නැත.",
  classDeleted: "පන්තිය මකා දැමුණා.",
  backToClasses: "පන්ති වෙත ආපසු",
  fromYourClasses: "ඔබේ පන්තිවලින්",
  classBookFrom: (name: string) => `${name} පන්තියෙන්`,
  // -- sharing a book with a class --------------------------------------------
  shareBook: "පන්තියක් සමඟ බෙදා ගන්න",
  shareHeading: (title: string) => `"${title}" බෙදා ගැනීම`,
  reviewHeading: "පරීක්ෂා කළ යුතු පිටු",
  reviewIntro:
    "මෙම පිටු පින්තූරයෙන් කියවා ඇති නිසා වැරදි තිබිය හැක. එක් එක් පිටුව පිළිගන්න, නැතහොත් නවත්වන්න. නවත්වන පිටු ඔබේ පන්තියට කියවනු නොලැබේ.",
  noReview: "පරීක්ෂා කළ යුතු පිටු නැත.",
  pageAccept: "පිළිගන්න",
  pageWithhold: "නවත්වන්න",
  undecidedCount: (count: number) => `තවම තීරණය නොකළ පිටු ${count}ක්`,
  basisHeading: "බෙදා ගැනීමේ අයිතිය",
  basisIntro: "මෙම පොත ඔබේ පන්තිය සමඟ බෙදා ගැනීමට ඔබට අයිතිය ඇත්තේ ඇයි? ඔබේ පිළිතුර සටහන් වේ.",
  basisName: (basis: string) =>
    ({
      public_domain: "ප්‍රකාශන හිමිකම ඉකුත් වූ කෘතියකි",
      government_textbook: "රජයේ පෙළපොතකි",
      publisher_permission: "ප්‍රකාශකයාගේ අවසරය ඇත",
      own_work: "මගේම කෘතියකි",
      other: "වෙනත්",
    })[basis] ?? basis,
  basisNoteLabel: "විස්තරය",
  basisNoteHint: '"වෙනත්" තෝරන්නේ නම් අවශ්‍යයි.',
  shareClassesLegend: "බෙදා ගන්නා පන්ති",
  noClassesToShare: "පළමුව පන්තියක් සාදන්න.",
  publishAction: "බෙදා ගන්න",
  published: "පොත පන්තිය සමඟ බෙදා ගත්තා.",
  errorUnreviewed: "පළමුව පරීක්ෂා කළ යුතු සියලු පිටු ගැන තීරණය කරන්න.",
  errorBasisNote: '"වෙනත්" සඳහා විස්තරයක් ලියන්න.',
  errorChooseClass: "අවම වශයෙන් එක් පන්තියක් තෝරන්න.",
  errorChooseBasis: "බෙදා ගැනීමේ අයිතිය තෝරන්න.",
  sharedWithHeading: "දැනට බෙදා ගෙන ඇත්තේ",
  notShared: "තවම කිසිම පන්තියක් සමඟ බෙදා ගෙන නැත.",
  stopSharingNamed: (name: string) => `${name} සමඟ බෙදා ගැනීම නවත්වන්න`,
  stoppedSharing: "බෙදා ගැනීම නැවැත්තුවා.",
  staleShare:
    "ඔබ බෙදා ගත් පසු පොත වෙනස් වී ඇත. පන්තිය තවමත් පෙර අනුවාදය කියවයි. නැවත බෙදා ගත්තොත් නව අනුවාදය ලැබේ.",
  prerenderHeading: "පන්තිය සඳහා හඬ",
  prerenderIntro:
    "පොතේ සියලු වාක්‍ය කලින්ම හඬට හරවන්න, එවිට සිසුන් ඇසීම ආරම්භ කරන විට බලා සිටීමට සිදු නොවේ. නවත්වන ලද පිටු හඬට හරවන්නේ නැත. නැවැත්තුවහොත්, නැවත ආරම්භ කළ විට නතර වූ තැන සිට ඉදිරියට යයි.",
  prerenderProgress: (ready: number, total: number) => `වාක්‍ය ${total} න් ${ready} ක් සූදානම්.`,
  prerenderDone: "සියලු වාක්‍ය සූදානම්.",
  prerenderAction: "දැන් හඬට හරවන්න",
  prerenderStarted: "හඬට හැරවීම ආරම්භ කළා. මෙයට යම් කාලයක් ගත විය හැක.",
  onlyTeachersShare: "පන්ති සමඟ බෙදා ගත හැක්කේ ගුරුවරුන්ට පමණි.",
  // Refusals, each saying what to do next.
  errorSignIn: "ඊමේල් ලිපිනය හෝ මුරපදය නිවැරදි නැත.",
  errorRecover: "ඊමේල් ලිපිනය හා ප්‍රතිසාධන කේතය නොගැළපේ.",
  errorEmailTaken: "මෙම ඊමේල් ලිපිනයට දැනටමත් ගිණුමක් ඇත. ඇතුළු වන්න, නැතහොත් ගිණුම නැවත ලබා ගන්න.",
  errorWeakPassword: (min: number) => `මුරපදය අවම වශයෙන් අකුරු ${min} ක් විය යුතුය.`,
  // The recovery code, shown once.
  recoveryCodeHeading: "ඔබේ ප්‍රතිසාධන කේතය",
  recoveryCodeIntro:
    "මුරපදය අමතක වුවහොත් ඔබේ ගිණුමට නැවත පිවිසිය හැකි ක්‍රමය මෙයයි. මෙය නැවත පෙන්වන්නේ නැත. පිටපත් කර හෝ ගොනුවක් ලෙස බාගෙන ආරක්ෂිත තැනක තබා ගන්න.",
  copyCode: "කේතය පිටපත් කරන්න",
  codeCopied: "කේතය පිටපත් කළා.",
  downloadCode: "ගොනුවක් ලෙස බාගන්න",
  savedCodeConfirm: "මම මෙම කේතය ආරක්ෂිතව තබා ගත්තෙමි",
  continueToLibrary: "මගේ පොත් වෙත යන්න",
  recoveryFileName: "swara-recovery-code.txt",
  recoveryFileText: (email: string, code: string) =>
    `ස්වර ප්‍රතිසාධන කේතය\n\nගිණුම: ${email}\nකේතය: ${code}\n\nමුරපදය අමතක වුවහොත් "ගිණුම නැවත ලබා ගන්න" පිටුවේ මෙය භාවිත කරන්න. භාවිත කළ පසු නව කේතයක් ලැබේ.\n`,

  // -- library -----------------------------------------------------------
  libraryHeading: "මගේ පොත්",
  libraryEmpty: "තවම පොත් නැත. පහතින් පොතක් එක් කරන්න.",
  uploadHeading: "පොතක් එක් කරන්න",
  uploadLabel: "PDF ගොනුවක් තෝරන්න",
  uploadHelp: "PDF, Word හෝ පින්තූර ගොනු එකක් හෝ කිහිපයක් එක් කරන්න. ඔබගේ ලේඛන පෞද්ගලිකයි.",
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
  publicNavigation: "ස්වර ගැන",
  footerNavigation: "වෙබ් අඩවියේ ප්‍රකාශ",
  howItWorksNav: "ක්‍රියා කරන ආකාරය",
  forTeachersNav: "ගුරුවරුන් සඳහා",
  helpNav: "උදව්",
  accessibilityNav: "ප්‍රවේශ්‍යතා ප්‍රකාශය",
  privacyNav: "පෞද්ගලිකත්වය",
  termsNav: "භාවිත නියම",
  homeTitle: "සිංහල අධ්‍යයන වේදිකාව",
  lastReviewed: (date: string) => `අවසන් වරට සමාලෝචනය කළේ: ${date}`,
  reportBarrier: "බාධකයක් හෝ ගැටලුවක් වාර්තා කරන්න",
  processingNowHeading: "මෙම සේවාදායකයේ දැන්",
  processingNowChecking: "සේවාදායකයේ සැකසුම් පරීක්ෂා කරමින්…",
  processingNowUnknown: "මෙම සේවාදායකයේ සැකසුම් දැන් පරීක්ෂා කළ නොහැක.",
  processingStructure: "පිටු ව්‍යුහය හඳුනා ගැනීම",
  processingAnswers: "ප්‍රශ්නවලට පිළිතුරු",
  processingOcr: "ස්කෑන් කළ පිටු කියවීම",
  processingHere: "ස්වර සේවාදායකය තුළම; පිටතට නොයයි",
  processingGoogle: "Google Gemini වෙත යවනු ලැබේ",
  processingOff: "ක්‍රියාත්මක නැත",
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
  // Where preparation has got to, and why it stopped.
  stageExtracting: "පිටු කියවමින්",
  stageRecognising: "පින්තූරවලින් අකුරු හඳුනාගනිමින්",
  stageStructuring: "වාක්‍ය ලෙස සකසමින්",
  failedStalled: "සූදානම් කිරීම අවසන් වීමට පෙර නතර විය. නැවත උත්සාහ කළ හැක.",
  failedRejected:
    "මෙම ගොනුව කියවිය නොහැක. එය හානි වී හෝ මුරපදයකින් ආරක්ෂා කර තිබිය හැක. වෙනත් පිටපතක් එක් කරන්න.",
  failedOther: "සූදානම් කිරීම අසාර්ථක විය. නැවත උත්සාහ කළ හැක.",
  bookFailed: (title: string) => `"${title}" සූදානම් කිරීම අසාර්ථක විය.`,
  retrying: "පොත නැවත සූදානම් කරමින්.",

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

  // -- contents (chapters) -------------------------------------------------
  // The heading is the design's. The two empty states are not in the design
  // and are the ones most in need of a native speaker's review: they are the
  // whole answer a reader gets when there is no list.
  contentsHeading: "අන්තර්ගතය",
  contentsOpen: "අන්තර්ගතය",
  chapterWord: "පරිච්ඡේදය",
  /** The book was examined and its layout shows no chapters. */
  contentsNone: "මෙම පොතේ පරිච්ඡේද හඳුනාගත නොහැකි විය. පිටුවෙන් පිටුවට හෝ පිටු අංකයෙන් ගමන් කරන්න.",
  /** Nobody looked: the book was prepared before chapters were detected. */
  contentsUnknown: "මෙම පොතේ පරිච්ඡේද ලැයිස්තුව තවම සකසා නැත.",
  /** In the header: "02 / title", as the design shows it. */
  currentChapter: (number: string | null, title: string) =>
    number ? `${number} / ${title}` : title,
  goToPageSubmit: "යන්න",
  /**
   * The reader's tab title until the book has loaded; then the tab is named
   * after the book itself. Distinct from every other page's title, so a
   * screen-reader user knows they are in the reader before the book arrives.
   */
  readingTitle: "පොත කියවීම",
  pageLoading: "පිටුව ලබා ගනිමින්…",
  sentencesHeading: "වාක්‍ය",
  sentenceCount: (count: number) => `වාක්‍ය ${count} ක්`,
  showWords: "වචන බලන්න",
  hideWords: "වචන සඟවන්න",
  sentenceWords: "වාක්‍යයේ වචන",
  wordCount: (count: number) => `වචන ${count} ක්`,
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
  errorSignedOut: "ඔබ ගිණුමෙන් ඉවත් වී ඇත. නැවත ඇතුළු වන්න.",
  errorForbidden: "මෙම පිටුව යල් පැන ගොස් ඇත. පිටුව නැවත පූරණය කර නැවත උත්සාහ කරන්න.",
  errorThrottled: "උත්සාහයන් බොහෝය. මඳ වේලාවකින් නැවත උත්සාහ කරන්න.",
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
    "PDF, Word හෝ පින්තූර ගොනුවක් එක් කරන්න. මුල් පිටුව එක් පසෙකත්, කියවිය හැකි සිංහල අකුර අනෙක් පසෙකත් පෙනේ. ඕනෑම වාක්‍යයක් තෝරා ඇහුම්කන් දෙන්න.",
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
  uploadFormats: "PDF, DOCX, PNG සහ JPEG — එක් වරකදී ගොනු කිහිපයක් තෝරාගත හැක.",
  uploadTooBig: "ගොනුව විශාල වැඩියි.",
  uploadNotPdf: "මෙය PDF ගොනුවක් නොවේ.",
  uploadUnsupported: "PDF, DOCX, PNG හෝ JPEG ගොනු පමණක් තෝරන්න.",
  uploadSelectedCount: (count: number) => `ගොනු ${count} ක් තෝරා ඇත.`,
  uploadSelectedFile: (filename: string) => `තෝරාගත් ගොනුව: ${filename}.`,
  uploadTitleLabel: "පොතේ නම (අත්‍යවශ්‍ය නොවේ)",
  uploadTitleHelp: "හිස් තැබුවහොත් ගොනුවේ නම භාවිත වේ.",
  uploadTitleSingleOnly: "නමක් දිය හැක්කේ එක් ගොනුවක් තෝරා ඇති විට පමණි.",
  fileSize: (bytes: number) => {
    const mb = bytes / (1024 * 1024);
    return mb >= 1
      ? `මෙගාබයිට් ${mb.toFixed(1)}`
      : `කිලෝබයිට් ${Math.max(1, Math.round(bytes / 1024))}`;
  },
  removeFile: "ගොනුව ඉවත් කරන්න",
  removeFiles: "ගොනු ඉවත් කරන්න",
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
  originalFailed: "මුල් ගොනුව ලබාගත නොහැක.",
  uploadedImageAlt: (filename: string) => `උඩුගත කළ පින්තූරය: ${filename}`,
  docxPreviewUnavailable: "Word ගොනුවේ කියවිය හැකි අකුරු දකුණු පස ඇත. මුල් ගොනුව මෙතැනින් බාගන්න.",
  downloadOriginal: "මුල් ගොනුව බාගන්න",
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
    case "signed_out":
      return strings.errorSignedOut;
    case "forbidden":
      return strings.errorForbidden;
    case "throttled":
      return strings.errorThrottled;
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

/**
 * What a book being prepared is doing, as its card shows it: "reading pages:
 * page 12 of 168", or just "preparing" before the first page is done.
 */
export function jobProgressMessage(job: Job | null): string {
  if (!job || job.pages_done === null || job.pages_total === null || job.pages_total <= 0) {
    return strings.stateRunning;
  }
  const stage =
    job.stage === "recognising"
      ? strings.stageRecognising
      : job.stage === "structuring"
        ? strings.stageStructuring
        : strings.stageExtracting;
  return `${stage}: ${strings.ofPages(job.pages_done, job.pages_total)}`;
}

/** Why a book stopped, in words a reader can act on. Never the server's detail. */
export function jobFailureMessage(job: Job | null): string {
  if (job?.stage === "stalled") return strings.failedStalled;
  if (job?.stage === "rejected") return strings.failedRejected;
  return strings.failedOther;
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
