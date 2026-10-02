/**
 * The front door's picture: a pen-and-ink landscape, an open book in the
 * foreground, and its voice rising off the page.
 *
 * Drawn, not filmed. The plan rules out autoplay and video on the front door
 * (docs/product-plan.md, the `/` row): moving pictures compete with the screen
 * reader and with a low-vision reader's attention, and cost a student's data
 * allowance before they have chosen to read anything. A still engraving gives
 * the same quiet, printed feel without any of that.
 *
 * Inline SVG in `currentColor`, so it has no white box to blend away and
 * follows the theme on its own: ink on paper in light, pale lines in dark.
 * Each layer is filled with the paper colour before it is hatched, so a nearer
 * hill hides the one behind it, as on a printed plate.
 *
 * Decorative: everything it says, the page says in words.
 */
/** Rounded trees on the far ridge: centre x, centre y, radius. */
const TREES: readonly (readonly [number, number, number])[] = [
  [1052, 218, 12],
  [1078, 214, 15],
  [1104, 220, 10],
  [612, 214, 11],
  [634, 210, 13],
];

/** Coconut palms on the middle hills: foot x, foot y, scale. */
const PALMS: readonly (readonly [number, number, number])[] = [
  [300, 262, 1],
  [1300, 254, 1.1],
  [1372, 258, 0.8],
];

/**
 * The scene's book and voice on their own, small, in a double ring: the mark
 * above the name on the front door. Decorative; the heading beside it is the
 * name.
 */
export function EngravedMark({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true" focusable="false">
      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="32" cy="32" r="30" strokeWidth="2.2" />
        <circle cx="32" cy="32" r="25.5" strokeWidth=".8" opacity=".5" />
        <path
          d="M32 36 C27 33.5 21 33.5 16 35 V44 C21 42.5 27 42.5 32 45 C37 42.5 43 42.5 48 44 V35 C43 33.5 37 33.5 32 36 Z"
          strokeWidth="1.6"
        />
        <path d="M32 36 V45" strokeWidth="1.2" />
        <path
          d="M19 38.5 Q25 37 29.5 39 M19 41.5 Q25 40 29.5 42 M34.5 39 Q39 37 45 38.5 M34.5 42 Q39 40 45 41.5"
          strokeWidth=".8"
          opacity=".75"
        />
        <path d="M27 29 A7 7 0 0 1 37 29" strokeWidth="1.6" />
        <path d="M23.5 25 A12 12 0 0 1 40.5 25" strokeWidth="1.3" opacity=".7" />
        <path
          d="M20 21 A17 17 0 0 1 44 21"
          strokeWidth="1.1"
          strokeDasharray="1.5 3.5"
          opacity=".55"
        />
      </g>
    </svg>
  );
}

export function EngravedScene({ className }: { className?: string }) {
  return (
    <svg
      className={className ? `engraved-scene ${className}` : "engraved-scene"}
      viewBox="0 0 1600 400"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <pattern id="hatch-far" width="8" height="7" patternUnits="userSpaceOnUse">
          <path d="M0 3.5 H8" stroke="currentColor" strokeWidth=".6" opacity=".45" />
        </pattern>
        <pattern
          id="hatch-mid"
          width="6"
          height="6"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(35)"
        >
          <path d="M0 3 H6" stroke="currentColor" strokeWidth=".7" opacity=".55" />
        </pattern>
        <pattern
          id="hatch-near"
          width="4"
          height="4"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(-30)"
        >
          <path d="M0 2 H4" stroke="currentColor" strokeWidth=".6" opacity=".6" />
        </pattern>
        <pattern id="hatch-dome" width="5" height="6" patternUnits="userSpaceOnUse">
          <path d="M2.5 0 V6" stroke="currentColor" strokeWidth=".6" opacity=".6" />
        </pattern>
      </defs>

      <g fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
        {/* A low sun, engraved as ruled lines inside a ring. Kept near the
            ridge so a short scene, cropped from the top, still shows it. */}
        <circle cx="1250" cy="146" r="24" strokeWidth="1.2" />
        <g strokeWidth=".7" opacity=".6">
          <path d="M1232 134 H1268 M1228 142 H1272 M1227 150 H1273 M1231 158 H1269" />
        </g>

        {/* Birds. */}
        <path d="M1090 158 q6 -7 12 0 q6 -7 12 0" strokeWidth="1.1" />
        <path d="M1130 140 q4 -5 8 0 q4 -5 8 0" strokeWidth="1" />
        <path d="M392 168 q5 -6 10 0 q5 -6 10 0" strokeWidth="1" />

        {/* Far ridge, with a dagoba on it. */}
        <path
          className="scene-paper"
          d="M0 236 C140 200 300 188 440 214 C560 236 680 196 800 198 C940 200 1040 236 1180 206 C1320 176 1460 168 1600 206 L1600 400 L0 400 Z"
        />
        <path
          fill="url(#hatch-far)"
          stroke="none"
          d="M0 236 C140 200 300 188 440 214 C560 236 680 196 800 198 C940 200 1040 236 1180 206 C1320 176 1460 168 1600 206 L1600 400 L0 400 Z"
        />
        <path
          d="M0 236 C140 200 300 188 440 214 C560 236 680 196 800 198 C940 200 1040 236 1180 206 C1320 176 1460 168 1600 206"
          strokeWidth="1.2"
        />
        <g strokeWidth="1.1">
          <path className="scene-paper" d="M470 226 A30 30 0 0 1 530 226 Z" />
          <path fill="url(#hatch-dome)" stroke="none" d="M470 226 A30 30 0 0 1 530 226 Z" />
          <path d="M470 226 A30 30 0 0 1 530 226" />
          <path d="M462 226 H538 M458 231 H542" />
          <path d="M494 197 V189 H506 V197" />
          <path d="M496 189 L500 162 L504 189" />
          <path d="M497 180 H503 M498 172 H502" strokeWidth=".8" />
        </g>
        {/* Rounded trees on the far ridge. */}
        <g strokeWidth="1">
          {TREES.map(([x, y, r]) => (
            <g key={`${x}-${y}`}>
              <circle className="scene-paper" cx={x} cy={y} r={r} />
              <circle fill="url(#hatch-mid)" stroke="none" cx={x} cy={y} r={r} />
              <circle cx={x} cy={y} r={r} />
              <path d={`M${x} ${y + r} V${y + r + 8}`} />
            </g>
          ))}
        </g>

        {/* Middle hills, dipping to a valley where the book lies. */}
        <path
          className="scene-paper"
          d="M0 296 C120 262 280 252 420 276 C540 296 660 326 800 324 C940 322 1060 290 1180 268 C1300 248 1460 262 1600 284 L1600 400 L0 400 Z"
        />
        <path
          fill="url(#hatch-mid)"
          stroke="none"
          d="M0 296 C120 262 280 252 420 276 C540 296 660 326 800 324 C940 322 1060 290 1180 268 C1300 248 1460 262 1600 284 L1600 400 L0 400 Z"
        />
        <path
          d="M0 296 C120 262 280 252 420 276 C540 296 660 326 800 324 C940 322 1060 290 1180 268 C1300 248 1460 262 1600 284"
          strokeWidth="1.3"
        />

        {/* Coconut palms. */}
        {PALMS.map(([x, y, s]) => (
          <g key={x} transform={`translate(${x} ${y}) scale(${s})`} strokeWidth="1.2">
            <path d="M0 0 C4 -33 12 -58 22 -80" />
            <path d="M3 -20 l5 1 M7 -40 l5 1 M13 -60 l5 1" strokeWidth=".8" />
            <path d="M22 -80 Q0 -90 -18 -78 M22 -80 Q6 -98 -10 -98 M22 -80 Q30 -100 50 -98 M22 -80 Q45 -90 60 -74 M22 -80 Q24 -100 16 -110" />
          </g>
        ))}

        {/* The near ground. */}
        <path
          className="scene-paper"
          d="M0 356 C220 336 460 344 640 346 C720 347 760 348 800 349 C980 350 1240 334 1600 352 L1600 400 L0 400 Z"
        />
        <path
          fill="url(#hatch-near)"
          stroke="none"
          d="M0 356 C220 336 460 344 640 346 C720 347 760 348 800 349 C980 350 1240 334 1600 352 L1600 400 L0 400 Z"
        />
        <path
          d="M0 356 C220 336 460 344 640 346 C720 347 760 348 800 349 C980 350 1240 334 1600 352"
          strokeWidth="1.3"
        />

        {/* The book: cover, two pages, its lines of text, and the ribbon. */}
        <g strokeWidth="1.4">
          <path className="scene-paper" d="M672 334 L800 352 L928 334 L922 326 L678 326 Z" />
          <path d="M672 334 L800 352 L928 334" />
          <path
            className="scene-paper"
            d="M800 300 C760 282 720 282 684 292 L684 330 C720 322 760 322 800 340 C840 322 880 322 916 330 L916 292 C880 282 840 282 800 300 Z"
          />
          <path d="M800 300 C760 282 720 282 684 292 L684 330 C720 322 760 322 800 340" />
          <path d="M800 300 C840 282 880 282 916 292 L916 330 C880 322 840 322 800 340" />
          <path d="M800 300 V340" />
          <path d="M684 330 L678 334 M916 330 L922 334" strokeWidth="1" />
        </g>
        <g strokeWidth=".9" opacity=".75">
          {[0, 1, 2, 3, 4].map((i) => (
            <g key={i}>
              <path d={`M700 ${298 + i * 6} Q742 ${290 + i * 6} 788 ${305 + i * 6}`} />
              <path d={`M812 ${305 + i * 6} Q858 ${290 + i * 6} 900 ${298 + i * 6}`} />
            </g>
          ))}
        </g>
        <path
          className="scene-ribbon"
          d="M801 340 C805 352 797 360 804 374 L799 371 M804 374 L806 367"
          strokeWidth="2"
        />

        {/* Its voice, rising off the page. */}
        <path d="M765.4 266 A40 40 0 0 1 834.6 266" strokeWidth="1.6" opacity=".85" />
        <path d="M737.6 250 A72 72 0 0 1 862.4 250" strokeWidth="1.3" opacity=".6" />
        <path
          d="M708.2 233 A106 106 0 0 1 891.8 233"
          strokeWidth="1.1"
          strokeDasharray="2 7"
          opacity=".5"
        />
      </g>
    </svg>
  );
}
