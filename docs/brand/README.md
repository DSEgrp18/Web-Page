# Icon sources

The app icon is a flat open book with the gold ribbon, on the brand green. It
replaced an illustrated book that blurred to nothing at 16 px and left a white
halo on a dark tab bar.

| File | Drawn for | Rendered to |
| --- | --- | --- |
| [`apps/web/public/brand/icon.svg`](../../apps/web/public/brand/icon.svg) | 32 px and up; served as-is to browsers that take SVG icons | `icon-32.png`, `icon-192.png`, `icon-512.png` |
| [`icon-16.svg`](icon-16.svg) | 16 px: a heavier book on its own grid, so the ribbon survives | `icon-16.png` |
| [`apple-icon.svg`](apple-icon.svg) | iOS: square and opaque, since iOS rounds the corners and fills transparency with black | `apple-icon.png` (180 px, RGB) |

The PNGs were rendered by headless Chromium at exactly their pixel size (not
scaled down from 512), then losslessly optimised. `apps/web/tests/icons.test.ts`
checks that each declared icon exists at its declared size.

The masthead mark (`swara-mark.webp`) and the other illustrations are unchanged.
