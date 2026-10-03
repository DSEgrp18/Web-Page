# The interface's fonts, self-hosted

Three variable fonts, loaded through `next/font/local` in `../layout.tsx`.

| File                    | Source in [google/fonts](https://github.com/google/fonts) at `9710da1eacb3` | Kept                                                            |
| ----------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `Yaldevi.woff2`         | `ofl/yaldevi/Yaldevi[wght].ttf`                                             | Weights 200–700; Sinhala, Latin, Latin Extended                 |
| `NotoSansSinhala.woff2` | `ofl/notosanssinhala/NotoSansSinhala[wdth,wght].ttf`                        | Weights 100–900 at normal width; Sinhala, Latin, Latin Extended |
| `PlusJakartaSans.woff2` | `ofl/plusjakartasans/PlusJakartaSans[wght].ttf`                             | Weights 200–800; Latin, Latin Extended                          |

All three are under the SIL Open Font License 1.1. Each licence sits beside its
font, as the licence requires.

Each file was subset to the characters above with **every OpenType layout
feature kept**, because Sinhala needs them to form its conjuncts and place its
vowel signs. Hinting was removed, and the Noto width axis was pinned at 100.
The Sinhala ranges are Google's own: U+0964-0965, U+0D81-0DF4, U+1CF2,
U+200C-200D (the joiners, which are part of Sinhala words), U+25CC and
U+111E1-111F4.

## Why not `next/font/google`

It fetches the fonts from Google while building. Google sometimes answers
with a dynamic `fonts.gstatic.com/l/font?kit=…&skey=…` address instead of a
static file, and the `&` in it breaks the query Turbopack builds ("next/font/google
queries have exactly one entry"). The dev server and the build then fail to
start, intermittently, on CI and locally, depending on what Google served. Files
in the repository build the same way every time, without the network, and
send no reader's request to Google.
