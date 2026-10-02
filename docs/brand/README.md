# Brand

Swara's mark is a roof over an open book, above the word ස්වර: royal blue for
the roof and the word, warm orange for the pages and the first letter. The
interface is built from the same two colours.

## The logo and everything made from it

[`logo-source.png`](logo-source.png) is the logo as supplied (2400 × 1800,
SHA-256 `e299d992b886c12775630399c06b2cb3f2de0c355f51687f6423241b0ee859e4`).
[`build-assets.py`](build-assets.py) makes every derived file from it:

| File in `apps/web/public/brand/` | What it is |
| --- | --- |
| `swara-lockup.webp` | The mark beside the word, for the masthead and footer |
| `swara-lockup-dark.webp` | The same with the blue lifted, for the dark theme |
| `icon.svg` | The mark traced to vector paths; browsers that take SVG icons use it |
| `icon-16.png`, `icon-32.png` | The mark, transparent |
| `icon-192.png`, `icon-512.png` | The mark on white, inside the maskable safe zone |
| `apple-icon.png` | 180 px, opaque RGB: iOS fills transparency with black |

```bash
python docs/brand/build-assets.py
```

`apps/web/tests/icons.test.ts` checks that each declared icon exists at its
declared size, and that the Apple icon is opaque.

## Colours

The logo's blue is `#2f53aa` and its orange `#fd9520`. Blue is the colour of
everything a reader can press. Orange measures 2.2:1 on white, so it is never
text on a light surface; `--accent-deep` (`#9a4d00`) carries the rare word that
must be orange. The full palette, for both themes, is the token block at the
top of `apps/web/src/app/globals.css`, and `apps/web/tests/tokens.contrast.test.ts`
measures every pair the stylesheet uses against WCAG 2.2 AA.

## Type

| Face | Used for |
| --- | --- |
| Yaldevi | Headings and display lines; geometric and rounded like the logo's lettering |
| Noto Sans Sinhala | Everything a reader reads, and every control |
| Plus Jakarta Sans | Latin in the interface: English, numbers, page counts |

All three are loaded through `next/font/google` in `apps/web/src/app/layout.tsx`.

## Photographs

From [Pexels](https://www.pexels.com/), under the
[Pexels license](https://www.pexels.com/license/): free to use and modify, no
attribution required. The license does not allow showing identifiable people
in a bad light or implying they endorse the product, and that applies to every
use of these pictures. The web copies in `apps/web/public/images/` are cropped
and compressed by `build-assets.py --photos <folder of originals>`.

| Web copy | Photograph | By |
| --- | --- | --- |
| `reading-desk-*.webp` | [9489804](https://www.pexels.com/photo/9489804/) | Yaroslav Shuraev |
| `study-notebook-*.webp` | [5797900](https://www.pexels.com/photo/5797900/) | Ann Poan |
| `student-laptop-*.webp` | [5905969](https://www.pexels.com/photo/5905969/) | Katerina Holmes |
| `student-tablet-*.webp` | [7694941](https://www.pexels.com/photo/7694941/) | Ksenia Chernaya |
| `colour-book-*.webp` | [3747300](https://www.pexels.com/photo/3747300/) | Polina Zimmerman |
| `classroom-*.webp` | [8617767](https://www.pexels.com/photo/8617767/) | Yan Krukov |

Every photograph is decoration: the page says in words whatever it suggests,
so each is `alt=""`, and no text is ever laid over one without a solid
background of its own.
