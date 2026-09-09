"""Build small PDFs in memory, so the tests need no committed binaries.

Extraction cannot be tested without PDFs, and PDFs are exactly what this
repository must never contain: ``scripts/verify-repo-hygiene.sh`` blocks
``*.pdf`` outright, because uploaded books and scanned private documents are the
things most expensive to leak into a public history. Checking in "harmless"
sample files would be the first crack in that rule.

So the fixtures are generated. This writes just enough PDF for pdfminer to parse
— a catalog, a page tree, content streams, and fonts — which turns out to be
about two hundred lines and buys far more than a folder of sample files would:

* **Sinhala without a Sinhala font.** Text is written with a Type0 font in
  ``Identity-H`` encoding, whose ``/ToUnicode`` map declares what each glyph
  code means. pdfminer reads that map and never looks at glyph outlines, so any
  code point can be produced without embedding — or licensing — a real font.
* **Legacy fonts on demand.** A page can claim to be set in ``FMAbhaya`` and
  emit the Latin characters such a file really contains. That case is the whole
  reason :mod:`sinhala_documents.fonts` exists and there is no other way to
  exercise it honestly.
* **Exact geometry and page labels.** Positions are chosen, not discovered, so a
  test can assert that a two-column page is detected as one.

The output is a plain uncompressed PDF 1.7 file. It is not a general writer and
should not become one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

#: A single grey pixel. Enough for pdfplumber to report an image on the page,
#: which is all the classifier needs to see.
_PIXEL = b"\xff"


@dataclass(frozen=True)
class Text:
    """One line of text placed on a page.

    ``y`` is measured from the bottom of the page, as PDF itself measures it,
    because these fixtures are written in PDF's terms. Extraction converts to
    top-down coordinates; asserting on the converted value is part of the point.
    """

    text: str
    font: str = "NotoSerifSinhala"
    size: float = 12.0
    x: float = 72.0
    y: float = 700.0


@dataclass(frozen=True)
class Page:
    """A page of the fixture document."""

    blocks: tuple[Text, ...] = ()
    images: int = 0
    width: float = 612.0
    height: float = 792.0


@dataclass
class _Objects:
    """A PDF object table that hands out numbers as bodies are added."""

    bodies: list[bytes] = field(default_factory=list)

    def reserve(self) -> int:
        self.bodies.append(b"")
        return len(self.bodies)

    def put(self, number: int, body: str | bytes) -> int:
        self.bodies[number - 1] = body if isinstance(body, bytes) else body.encode("latin-1")
        return number

    def add(self, body: str | bytes) -> int:
        return self.put(self.reserve(), body)

    def stream(self, header: str, payload: str | bytes) -> int:
        data = payload if isinstance(payload, bytes) else payload.encode("latin-1")
        body = f"<< {header} /Length {len(data)} >>\nstream\n".encode("latin-1")
        return self.add(body + data + b"\nendstream")


def _tounicode(codes: dict[str, int]) -> str:
    """A CMap declaring what each glyph code in the font means.

    This is the entire reason no font file is needed: pdfminer resolves text
    through this table, not through glyph outlines.
    """
    pairs = "\n".join(f"<{code:04X}> <{ord(character):04X}>" for character, code in codes.items())
    return (
        "/CIDInit /ProcSet findresource begin\n"
        "12 dict begin\nbegincmap\n"
        "/CMapName /Fixture def\n/CMapType 2 def\n"
        "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
        f"{len(codes)} beginbfchar\n{pairs}\nendbfchar\n"
        "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend"
    )


def _font_objects(objects: _Objects, name: str, characters: str) -> tuple[int, dict[str, int]]:
    """Emit a Type0 font covering ``characters`` and return its object number."""
    codes = {character: index + 1 for index, character in enumerate(dict.fromkeys(characters))}
    font = objects.reserve()
    descendant = objects.reserve()
    descriptor = objects.reserve()
    tounicode = objects.stream("", _tounicode(codes))

    objects.put(
        font,
        f"<< /Type /Font /Subtype /Type0 /BaseFont /{name} /Encoding /Identity-H "
        f"/DescendantFonts [{descendant} 0 R] /ToUnicode {tounicode} 0 R >>",
    )
    objects.put(
        descendant,
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{name} "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/FontDescriptor {descriptor} 0 R /DW 600 >>",
    )
    objects.put(
        descriptor,
        f"<< /Type /FontDescriptor /FontName /{name} /Flags 4 "
        f"/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 900 /Descent -200 "
        f"/CapHeight 700 /StemV 80 >>",
    )
    return font, codes


def _page_labels_tree(labels: list[tuple[int, str]]) -> str:
    """``/PageLabels`` from ``(page index, style)`` pairs such as ``(0, "r")``."""
    entries = " ".join(f"{index} << /S /{style} >>" for index, style in labels)
    return f"<< /Nums [{entries}] >>"


def build_pdf(
    pages: list[Page],
    *,
    labels: list[tuple[int, str]] | None = None,
    encrypted: bool = False,
) -> bytes:
    """Assemble ``pages`` into PDF bytes.

    ``labels`` declares printed page numbering the way a real book does: a list
    of ``(page index, style)`` pairs, where the style is one of the PDF codes
    ``D``, ``R``, ``r``, ``A`` or ``a``, each applying until the next entry.

    ``encrypted`` attaches a standard security handler whose stored password
    hashes are deliberate nonsense, so opening it with the empty password fails
    exactly as a real password-protected book does. Producing a genuinely
    decryptable file would mean implementing the handler; producing one that
    correctly refuses to open needs only that the check not pass.
    """
    objects = _Objects()
    catalog = objects.reserve()
    tree = objects.reserve()

    # One font object per distinct name, covering every character used with it.
    used: dict[str, str] = {}
    for page in pages:
        for block in page.blocks:
            used[block.font] = used.get(block.font, "") + block.text
    fonts = {name: _font_objects(objects, name, text) for name, text in used.items()}

    image = objects.stream(
        "/Type /XObject /Subtype /Image /Width 1 /Height 1 "
        "/ColorSpace /DeviceGray /BitsPerComponent 8",
        _PIXEL,
    )

    page_numbers: list[int] = []
    for page in pages:
        number = objects.reserve()
        page_numbers.append(number)

        operations: list[str] = []
        for block in page.blocks:
            codes = fonts[block.font][1]
            glyphs = "".join(f"{codes[character]:04X}" for character in block.text)
            operations.append(
                f"BT /F{list(used).index(block.font)} {block.size} Tf "
                f"{block.x} {block.y} Td <{glyphs}> Tj ET"
            )
        for index in range(page.images):
            operations.append(f"q 80 0 0 60 {72 + index * 100} 100 cm /Im0 Do Q")
        content = objects.stream("", "\n".join(operations))

        font_resources = " ".join(
            f"/F{position} {fonts[name][0]} 0 R" for position, name in enumerate(used)
        )
        resources = f"/Font << {font_resources} >>"
        if page.images:
            resources += f" /XObject << /Im0 {image} 0 R >>"
        objects.put(
            number,
            f"<< /Type /Page /Parent {tree} 0 R "
            f"/MediaBox [0 0 {page.width} {page.height}] "
            f"/Resources << {resources} >> /Contents {content} 0 R >>",
        )

    kids = " ".join(f"{number} 0 R" for number in page_numbers)
    objects.put(tree, f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")

    catalog_body = f"<< /Type /Catalog /Pages {tree} 0 R"
    if labels:
        catalog_body += f" /PageLabels {objects.add(_page_labels_tree(labels))} 0 R"
    objects.put(catalog, catalog_body + " >>")

    encrypt = objects.add(_ENCRYPT_DICT) if encrypted else None
    return _serialise(objects, catalog, encrypt)


#: A standard security handler, 40-bit RC4, with unusable password hashes.
_ENCRYPT_DICT = "<< /Filter /Standard /V 1 /R 2 /O <{o}> /U <{u}> /P -1 >>".format(
    o="11" * 32, u="22" * 32
)

#: An encrypted file must carry a document ID: the handler derives its key from
#: the first element.
_DOCUMENT_ID = "00" * 16


def _serialise(objects: _Objects, catalog: int, encrypt: int | None = None) -> bytes:
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects.bodies, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

    start = len(out)
    out += f"xref\n0 {len(objects.bodies) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode("latin-1")
    trailer = f"/Size {len(objects.bodies) + 1} /Root {catalog} 0 R"
    if encrypt is not None:
        trailer += f" /Encrypt {encrypt} 0 R /ID [<{_DOCUMENT_ID}> <{_DOCUMENT_ID}>]"
    out += f"trailer\n<< {trailer} >>\nstartxref\n{start}\n%%EOF\n".encode("latin-1")
    return bytes(out)


# --------------------------------------------------------------------------
# Ready-made pages for the cases that come up repeatedly
# --------------------------------------------------------------------------

#: A Unicode Sinhala page. The font name is a real Unicode Sinhala face, so the
#: legacy identifier must leave it alone.
SINHALA_LINES = (
    "පොත් කියවීම මගින් දැනුම වර්ධනය වේ.",
    "සෑම දිනකම ස්වල්ප වේලාවක් කියවීමට වෙන් කරන්න.",
)

#: What a pre-Unicode FM-Abhaya page really contains once extracted: Latin
#: letters and Latin-1 symbols standing in for Sinhala glyphs.
LEGACY_LINE = "fmdñl mßiaÑ;h yd tu ldrKh ù we;"


def sinhala_page(*, images: int = 0) -> Page:
    return Page(
        blocks=tuple(
            Text(line, font="NotoSerifSinhala", y=700 - index * 20)
            for index, line in enumerate(SINHALA_LINES)
        ),
        images=images,
    )


def legacy_page(font: str = "ABCDEF+FMAbhaya") -> Page:
    return Page(blocks=(Text(LEGACY_LINE, font=font, y=700),))


def two_column_page() -> Page:
    """Two columns of prose with a wide gutter between them."""
    left = tuple(Text("පොත් කියවීම මගින් දැනුම", x=60, y=700 - index * 16) for index in range(12))
    right = tuple(Text("වර්ධනය වන අතර එය සිතීමේ", x=330, y=700 - index * 16) for index in range(12))
    return Page(blocks=left + right)
