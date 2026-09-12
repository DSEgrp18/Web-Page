"""Structure inference through Gemini.

This sends a page of a reader's document to Google. That is external processing
of private material and is treated as such: it is off by default, it is selected
by configuration, it has a page size limit, and what comes back is not believed.

**Nothing here is trusted.** The prompt asks the model to copy text exactly, and
:func:`sinhala_documents.blocks.verify` checks that it did. The instruction is
how you get a good answer; the check is why a bad one cannot hurt anybody. If
this module were deleted the reader would keep working, which is the property
CLAUDE.md requires of the deterministic path.

Implemented on :mod:`urllib.request` rather than an HTTP library. It is one
POST, and this package's only dependency today is pdfplumber; adding a second
in order to send a JSON body would be a poor trade.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable

from .blocks import Block
from .ocr import OcrAdapter, OcrUnavailable
from .structure import BlockRole
from .structuring import StructureAdapter, StructureUnavailable

#: Bump on any change to the prompt, the schema, or the parsing below. It is
#: part of the adapter version, so it reaches provenance and cache identity:
#: a page structured by a different prompt is a different structuring.
PROMPT_VERSION = "1"

API_KEY_ENV = "GEMINI_API_KEY"
MODEL_ENV = "SINHALA_READER_STRUCTURE_MODEL"
DEFAULT_MODEL = "gemini-2.5-flash"

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

#: Pages longer than this are not sent. A cost and blast-radius limit rather
#: than a model limit: a page of a textbook is a few thousand characters, and
#: something far larger is a sign that extraction went wrong, which is not worth
#: paying to have structured.
MAX_PAGE_CHARACTERS = 20_000

REQUEST_TIMEOUT_SECONDS = 30

#: The roles the model may use. Deliberately not every BlockRole: RUNNING_HEAD
#: and PAGE_NUMBER decide what is *not* narrated, and a model that over-applies
#: them silently removes text from the audio. Those stay deterministic.
_OFFERED_ROLES = (
    BlockRole.HEADING,
    BlockRole.PARAGRAPH,
    BlockRole.CAPTION,
    BlockRole.LIST_ITEM,
    BlockRole.CONTENTS_ROW,
    BlockRole.TABLE_CELL,
    BlockRole.ADDRESS,
)

_INSTRUCTIONS = """\
You are given the text extracted from one page of a Sinhala school textbook.

Divide it into blocks and label each one. Return every part of the page exactly
once, in the order it should be read aloud.

Rules, in order of importance:

1. Copy the text character for character. Do not correct spelling, do not fix
   what looks like an extraction error, do not add or remove punctuation, do not
   complete an unfinished sentence, and do not translate anything. If a word
   looks wrong, it stays wrong. Your output is checked against the input and the
   whole page is discarded if a single character differs.
2. Do not invent a block. Every block's text must appear in the input.
3. Do not drop anything. Every character of the input must appear in exactly one
   block.
4. A figure or table caption is its own block, never part of the paragraph
   beside it. This matters more than any other labelling decision: a caption
   left inside a paragraph is read out in the middle of a sentence, to somebody
   who cannot see that it happened.
5. A heading carries a level: 1 for a chapter title, 2 for a section, 3 below
   that. Only headings carry a level.
6. A row of a table of contents is contents_row, including its page number.
7. Text that is genuinely a paragraph is paragraph. Do not reach for an exotic
   label when prose is the answer.

Line breaks in the input come from the page layout. Joining the lines of one
paragraph is expected and is not a change to the text.
"""


def _schema() -> dict:
    return {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": [role.value for role in _OFFERED_ROLES]},
                "level": {"type": "integer"},
                "text": {"type": "string"},
            },
            "required": ["role", "text"],
        },
    }


def _post(url: str, body: dict, *, timeout: int, api_key: str) -> dict:
    """One JSON POST. Separated so tests can replace it without a network.

    The key travels in a header rather than the query string, which would
    otherwise be recorded by proxies and repeated back inside error messages.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


class GeminiStructure(StructureAdapter):
    """Structure a page with Gemini, or say clearly that it could not.

    Every failure is :class:`StructureUnavailable`: no key, no network, a rate
    limit, a timeout, a malformed reply. The caller's response to all of them is
    the same - use the deterministic structure - and distinguishing them here
    would only invite somebody to retry the ones that will never succeed.

    A *wrong* answer is not raised. It is returned, and fails verification,
    which is a different outcome on purpose.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        post: Callable[..., dict] | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        self._model = model or os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL
        self._post = post or _post

    @property
    def version(self) -> str:
        return f"gemini/{self._model}/prompt-{PROMPT_VERSION}"

    def blocks_for(self, page_text: str) -> tuple[Block, ...]:
        if not page_text.strip():
            return ()
        if not self._api_key:
            raise StructureUnavailable(f"{API_KEY_ENV} is not set")
        if len(page_text) > MAX_PAGE_CHARACTERS:
            raise StructureUnavailable(
                f"page is {len(page_text)} characters, over the {MAX_PAGE_CHARACTERS} limit"
            )

        body = {
            "contents": [{"parts": [{"text": f"{_INSTRUCTIONS}\n\n---\n\n{page_text}"}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _schema(),
                # Structure is a reading of a fixed page, not a creative task,
                # and a stable answer is one a cache key can mean something
                # about.
                "temperature": 0,
            },
        }
        try:
            payload = self._post(
                ENDPOINT.format(model=self._model),
                body,
                timeout=REQUEST_TIMEOUT_SECONDS,
                api_key=self._api_key,
            )
        except urllib.error.HTTPError as error:
            raise StructureUnavailable(f"structure request failed: HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise StructureUnavailable(f"structure request failed: {error}") from error

        return _parse(payload)


def _parse(payload: dict) -> tuple[Block, ...]:
    """Turn a Gemini response into blocks, or say it could not be read.

    Deliberately unforgiving. A reply that does not match the schema is a reply
    nobody should be guessing about, and guessing is how a misparse turns into a
    page of the wrong structure that still verifies.
    """
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as error:
        # Includes the safety-blocked case, where there are no parts at all.
        raise StructureUnavailable("structure response had no content") from error

    try:
        items = json.loads(text)
    except json.JSONDecodeError as error:
        raise StructureUnavailable("structure response was not JSON") from error

    if not isinstance(items, list):
        raise StructureUnavailable("structure response was not a list of blocks")

    blocks: list[Block] = []
    for item in items:
        if not isinstance(item, dict):
            raise StructureUnavailable("a block in the structure response was not an object")
        try:
            role = BlockRole(item["role"])
        except (KeyError, ValueError) as error:
            raise StructureUnavailable(f"unknown block role: {item.get('role')!r}") from error
        body = item.get("text")
        if not isinstance(body, str):
            raise StructureUnavailable("a block in the structure response had no text")

        level = item.get("level")
        if role is BlockRole.HEADING:
            # A heading whose level the model omitted is still a heading. The
            # deepest level is the safe default: it nests under whatever came
            # before, instead of restructuring the document around itself.
            level = level if isinstance(level, int) and 1 <= level <= 6 else 3
        else:
            level = None
        blocks.append(Block(role=role, text=body, level=level))
    return tuple(blocks)


#: Bump on any change to the OCR prompt or its parsing. Part of the OCR version,
#: and therefore of extraction provenance and cache identity.
OCR_PROMPT_VERSION = "1"

_OCR_INSTRUCTIONS = """\
This is a photograph of one page of a Sinhala school textbook.

Transcribe the Sinhala text on it, in reading order.

Rules:

1. Transcribe only what is on the page. Do not translate, do not summarise, do
   not complete a sentence that is cut off, and do not add anything that is not
   printed there.
2. Write proper Sinhala Unicode. The page may be typeset in an old font, but
   what you return must be ordinary Sinhala script.
3. Keep the line breaks of the page.
4. If a word is genuinely unreadable, write it as best you can. Do not invent a
   plausible sentence around it.
5. Ignore page furniture that is not part of the text: nothing else.
6. Return only the transcription, with no commentary, no preamble, and no
   markdown fences.
"""


class GeminiOcr(OcrAdapter):
    """Read a rendered page with Gemini, or say clearly that it could not.

    Unlike the structure adapter, **there is nothing to verify this against**.
    Structure could be checked character for character against text we already
    had; a page that had no usable text has no such reference, which is the
    whole reason it is here. So its output is always marked for review, and the
    honest limit of this class is that it cannot tell a correct transcription
    from a fluent invention. A recogniser that is wrong and a recogniser that is
    right look identical from here.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        post: Callable[..., dict] | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        self._model = model or os.environ.get(MODEL_ENV, "").strip() or DEFAULT_MODEL
        self._post = post or _post

    @property
    def version(self) -> str:
        return f"gemini-ocr/{self._model}/prompt-{OCR_PROMPT_VERSION}"

    def text_for(self, image_png: bytes) -> str:
        if not self._api_key:
            raise OcrUnavailable(f"{API_KEY_ENV} is not set")
        if not image_png:
            raise OcrUnavailable("nothing was rendered for this page")

        body = {
            "contents": [
                {
                    "parts": [
                        {"text": _OCR_INSTRUCTIONS},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": base64.b64encode(image_png).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            # Transcription is a reading of a fixed image, not a creative task.
            "generationConfig": {"temperature": 0},
        }
        try:
            payload = self._post(
                ENDPOINT.format(model=self._model),
                body,
                timeout=REQUEST_TIMEOUT_SECONDS,
                api_key=self._api_key,
            )
        except urllib.error.HTTPError as error:
            raise OcrUnavailable(f"OCR request failed: HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise OcrUnavailable(f"OCR request failed: {error}") from error

        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise OcrUnavailable("OCR response had no content") from error
        if not isinstance(text, str) or not text.strip():
            # An empty transcription would be stored as a page with nothing on
            # it, which a reader experiences as the book skipping a page.
            raise OcrUnavailable("OCR returned no text")
        return text.strip()
