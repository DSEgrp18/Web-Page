"""A fixed set of Sinhala sentences for inference regression checks.

CLAUDE.md requires a fixed Sinhala inference regression set, run before an
inference release and compared against a known-good baseline. This is its
starting point: small, deliberate, and chosen so each entry can fail for a
reason someone can name.

It is not an evaluation set. Evaluation needs hundreds of held-out sentences and
human listening; this is a smoke test that answers "did the model load, and does
it still produce plausible audio for the cases we know are risky".

Keep it stable. Adding cases is fine; changing or removing one breaks comparison
against every baseline recorded before the change, so do that in a commit that
says why.

Generation is stochastic, so output is **not** byte-identical between runs.
Never assert on exact samples. Compare duration, the audio checks, and human
listening.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    text: str
    why: str
    # Whether the text is a single sentence, so appended audio after it is a
    # fault rather than the second sentence being narrated correctly. Set
    # False for multi-sentence cases; the appended-audio check is skipped for
    # them because flagging them would be a false positive.
    single_utterance: bool = True


CASES: tuple[RegressionCase, ...] = (
    RegressionCase(
        case_id="plain-short",
        text="මම ගෙදර යනවා.",
        why="The simplest possible case. If this fails, nothing else matters.",
    ),
    RegressionCase(
        case_id="plain-longer",
        text="අද දවසේ කාලගුණය ඉතා හොඳයි. අපි උදෑසන පාසල් ගියෙමු.",
        why="Two sentences, to check the model does not stop after the first.",
        single_utterance=False,
    ),
    RegressionCase(
        case_id="page-reference",
        text="පිටුව 42 බලන්න.",
        why=(
            "The defect that motivated the normaliser. Without number expansion "
            "this narrates as 'look at page' with no number. Listen for "
            "'හතළිස් දෙක'."
        ),
    ),
    RegressionCase(
        case_id="year",
        text="2024 වර්ෂයේ දී එය සිදු විය.",
        why="A year, the most common number in a textbook. Listen for 'දෙදහස් විසි හතර'.",
    ),
    RegressionCase(
        case_id="decimal-and-percent",
        text="ප්‍රතිශතය 12.5% ක් විය.",
        why=(
            "Decimal read digit by digit after දශම, and the percent marker moving "
            "in front of the number. Also carries a ZWJ conjunct in ප්‍ර."
        ),
    ),
    RegressionCase(
        case_id="mixed-english",
        text="මෙය PDF ලේඛනයකි.",
        why=(
            "English inside Sinhala, which survives romanisation intact. Listen "
            "for whether 'PDF' is recognisable."
        ),
    ),
    RegressionCase(
        case_id="conjuncts",
        text="ක්‍ෂේත්‍රය පිළිබඳ ඥානය ලබා ගන්න.",
        why="Dense conjuncts and ZWJ, where the romanisation is most likely to be wrong.",
    ),
    RegressionCase(
        case_id="comma-clauses",
        text="අද, මම පාසල් ගොස්, පසුව ගෙදර ආවෙමි.",
        why=(
            "One sentence with two commas, so it contains real internal pauses. "
            "This is the case that would expose trailing-audio trimming cutting "
            "genuine speech: listen for whether it ends mid-sentence."
        ),
    ),
    RegressionCase(
        case_id="long-single-sentence",
        text=(
            "පොත් කියවීම මගින් දැනුම වර්ධනය වන අතර, එය සිතීමේ හැකියාව ද "
            "වර්ධනය කරන බැවින්, සෑම දිනකම ස්වල්ප වේලාවක් කියවීමට වෙන් කර ගැනීම "
            "ඉතා වැදගත් වේ."
        ),
        why=(
            "A long single sentence with several clauses. Tests both the "
            "false-cut risk from internal pauses and how close a realistic "
            "sentence comes to the model's utterance ceiling."
        ),
    ),
    RegressionCase(
        case_id="line-broken",
        text="මෙම වාක්‍යය\nදෙකට කැඩී\nඇත.",
        why=(
            "Line breaks as a PDF extraction would produce them. Without "
            "whitespace normalisation the words either side are joined."
        ),
    ),
)


def case_by_id(case_id: str) -> RegressionCase:
    for case in CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(f"no regression case {case_id!r}")
