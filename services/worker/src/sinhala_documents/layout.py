"""Notice when flattened extraction has probably scrambled the reading order.

pdfminer returns characters roughly top-to-bottom, left-to-right. On a
two-column page that interleaves the columns: line one of the left column, then
line one of the right column, then line two of the left. The text looks
plausible, every word is present, and the sentences are nonsense. Narrated
aloud, it is worse than a blank page, because a blank page announces itself.

Reordering columns properly is a layout-analysis problem and is not attempted
here. What this module does is cheaper and more honest: find the white gutter
that a multi-column page must have, and let the page say it is unsure. CLAUDE.md
requires layout ambiguity to be handled explicitly rather than assumed away, and
an announced uncertainty is a thing a reader can work around.
"""

from __future__ import annotations

from collections.abc import Sequence

#: A gutter must be at least this fraction of the page wide. Narrower gaps are
#: ordinary word spacing and inter-paragraph indentation.
MIN_GUTTER_FRACTION = 0.035

#: ...and at least this many points, so a narrow page cannot produce a gutter
#: out of a single wide space.
MIN_GUTTER_POINTS = 18.0

#: Only the middle of the page is searched. Margins are gutters by definition
#: and say nothing about columns.
_SEARCH_BAND = (0.18, 0.82)

#: Both sides must carry real text. Without this, a centred heading over a full
#: width paragraph reads as two columns.
_MIN_CHARS_PER_SIDE = 25

#: Vertical overlap between the two sides, as a fraction of the shorter side.
#: Genuine columns run alongside each other; a figure beside a caption does not.
_MIN_VERTICAL_OVERLAP = 0.5


def _vertical_extent(chars: Sequence[dict]) -> tuple[float, float]:
    return min(c["top"] for c in chars), max(c["bottom"] for c in chars)


def find_gutter(chars: Sequence[dict], page_width: float) -> tuple[float, float] | None:
    """The widest empty vertical band that could separate two columns.

    Returns its ``(x0, x1)``, or ``None`` when the page shows no sign of being
    laid out in columns.
    """
    if page_width <= 0 or len(chars) < _MIN_CHARS_PER_SIDE * 2:
        return None

    width = int(page_width) + 1
    occupied = bytearray(width)
    for char in chars:
        left = max(0, min(width - 1, int(char["x0"])))
        right = max(0, min(width - 1, int(char["x1"]) + 1))
        for column in range(left, right + 1):
            occupied[column] = 1

    low = int(page_width * _SEARCH_BAND[0])
    high = int(page_width * _SEARCH_BAND[1])
    minimum = max(page_width * MIN_GUTTER_FRACTION, MIN_GUTTER_POINTS)

    best: tuple[float, float] | None = None
    run_start: int | None = None
    for column in range(low, high + 1):
        if not occupied[column]:
            run_start = column if run_start is None else run_start
            continue
        if run_start is not None:
            if column - run_start >= minimum and (
                best is None or column - run_start > best[1] - best[0]
            ):
                best = (float(run_start), float(column))
            run_start = None
    if run_start is not None and high + 1 - run_start >= minimum:
        candidate = (float(run_start), float(high + 1))
        if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
            best = candidate
    return best


def suspects_multiple_columns(chars: Sequence[dict], page_width: float) -> bool:
    """Whether this page's reading order should be treated as uncertain.

    A gutter alone is not enough. The text on either side of it has to be
    substantial and has to run alongside the other side vertically, which is
    what distinguishes two columns of prose from an image with a caption
    beside it.
    """
    gutter = find_gutter(chars, page_width)
    if gutter is None:
        return False

    left = [c for c in chars if c["x1"] <= gutter[0]]
    right = [c for c in chars if c["x0"] >= gutter[1]]
    if len(left) < _MIN_CHARS_PER_SIDE or len(right) < _MIN_CHARS_PER_SIDE:
        return False

    left_top, left_bottom = _vertical_extent(left)
    right_top, right_bottom = _vertical_extent(right)
    overlap = min(left_bottom, right_bottom) - max(left_top, right_top)
    shorter = min(left_bottom - left_top, right_bottom - right_top)
    if shorter <= 0:
        return False
    return overlap / shorter >= _MIN_VERTICAL_OVERLAP
