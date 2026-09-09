"""The page numbers a reader would see printed on the page.

A book's front matter is numbered separately from its body, so the twelfth page
of a PDF is routinely printed "vi", and page 1 of the body is somewhere in the
middle of the file. A reader who asks to go to page 42, or who is told a quoted
passage came from page 42, means the printed number. The file position is an
implementation detail they never see.

PDF stores this as a number tree under ``/PageLabels`` mapping the index of each
page where numbering *changes* to a style, an optional prefix, and a starting
value. Everything after it continues in that style until the next entry. That is
the whole format; it is small, and it is the only place the information exists.

Absent ``/PageLabels`` — most single-article PDFs — there is no printed label to
report, and this returns ``None`` for every page rather than inventing one from
the file position.
"""

from __future__ import annotations

from pdfminer.pdftypes import resolve1

#: Roman numeral values, largest first, including the subtractive forms.
_ROMAN = (
    (1000, "m"),
    (900, "cm"),
    (500, "d"),
    (400, "cd"),
    (100, "c"),
    (90, "xc"),
    (50, "l"),
    (40, "xl"),
    (10, "x"),
    (9, "ix"),
    (5, "v"),
    (4, "iv"),
    (1, "i"),
)


def _roman(value: int) -> str:
    if value <= 0:
        return ""
    out = []
    for amount, numeral in _ROMAN:
        count, value = divmod(value, amount)
        out.append(numeral * count)
    return "".join(out)


def _letters(value: int) -> str:
    """A, B, ... Z, AA, BB — the repetition the PDF specification prescribes."""
    if value <= 0:
        return ""
    index, repeats = (value - 1) % 26, (value - 1) // 26 + 1
    return chr(ord("a") + index) * repeats


def _format(style: str | None, number: int) -> str:
    match style:
        case "D":
            return str(number)
        case "R":
            return _roman(number).upper()
        case "r":
            return _roman(number)
        case "A":
            return _letters(number).upper()
        case "a":
            return _letters(number)
        case _:
            # No style means prefix only. A page labelled purely by its prefix
            # is legal and appears in appendices ("Appendix A" with no number).
            return ""


def _decode(value: object) -> str:
    if isinstance(value, bytes):
        # PDF text strings are PDFDoc-encoded unless they carry a UTF-16 mark.
        if value[:2] in (b"\xfe\xff", b"\xff\xfe"):
            return value.decode("utf-16", errors="replace")
        return value.decode("latin-1", errors="replace")
    return str(value)


def _walk(node: object, into: dict[int, dict]) -> None:
    """Collect every ``index -> label dictionary`` entry in a number tree."""
    node = resolve1(node)
    if not isinstance(node, dict):
        return
    nums = resolve1(node.get("Nums"))
    if isinstance(nums, list):
        for index in range(0, len(nums) - 1, 2):
            key = resolve1(nums[index])
            entry = resolve1(nums[index + 1])
            if isinstance(key, int) and isinstance(entry, dict):
                into[key] = entry
    for kid in resolve1(node.get("Kids")) or []:
        _walk(kid, into)


def page_labels(document: object, page_count: int) -> list[str | None]:
    """Printed labels for every page, ``None`` where the PDF declares none.

    ``document`` is a pdfminer ``PDFDocument``; a file without ``/PageLabels``,
    or with one this cannot parse, yields all ``None``. A malformed numbering
    tree is not a reason to reject a book — it costs citations their printed
    page number and nothing else — so failures here are silent by design.
    """
    try:
        catalog = getattr(document, "catalog", None) or {}
        ranges: dict[int, dict] = {}
        _walk(catalog.get("PageLabels"), ranges)
    except Exception:  # noqa: BLE001 - a broken label tree must not lose the book
        return [None] * page_count

    if not ranges:
        return [None] * page_count

    labels: list[str | None] = []
    style: str | None = None
    prefix = ""
    start = 1
    origin = 0
    for index in range(page_count):
        if index in ranges:
            entry = ranges[index]
            raw_style = resolve1(entry.get("S"))
            style = raw_style.name if hasattr(raw_style, "name") else None
            prefix = _decode(resolve1(entry.get("P")) or "")
            start = resolve1(entry.get("St"))
            start = start if isinstance(start, int) else 1
            origin = index
        label = prefix + _format(style, start + index - origin)
        labels.append(label or None)
    return labels
