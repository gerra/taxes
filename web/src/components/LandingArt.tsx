// Vector artwork for the landing page. Everything is inline SVG so it inherits
// the palette from index.css (var(--coral) etc.) and stays crisp at any size.

// A mock of what the app produces: an SA108 card with real-looking boxes, a
// pool chart peeking out from behind it, and a "matched" pill floating on top.
export function HeroArt() {
  return (
    <svg
      className="hero-art-svg"
      viewBox="0 0 480 400"
      role="img"
      aria-label="An illustration of a finished capital gains summary, with the Self Assessment box numbers filled in"
    >
      <defs>
        <filter id="cardShadow" x="-25%" y="-25%" width="150%" height="160%">
          <feDropShadow dx="0" dy="14" stdDeviation="16" floodColor="#191521" floodOpacity="0.10" />
        </filter>
        <filter id="chipShadow" x="-40%" y="-60%" width="180%" height="240%">
          <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#191521" floodOpacity="0.12" />
        </filter>
        <linearGradient id="barFill" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="var(--mint)" stopOpacity="0.55" />
          <stop offset="100%" stopColor="var(--mint)" />
        </linearGradient>
      </defs>

      {/* Soft shapes behind everything, the way Freetrade backs its screenshots. */}
      <g className="hero-blobs" aria-hidden="true">
        <circle cx="392" cy="92" r="100" fill="var(--coral-soft)" />
        <circle cx="74" cy="316" r="84" fill="var(--mint-soft)" />
        <circle cx="248" cy="24" r="44" fill="var(--lilac-soft)" />
      </g>

      {/* The report card. Everything else overlaps only its padding, never a figure. */}
      <g filter="url(#cardShadow)">
        <rect x="150" y="26" width="310" height="316" rx="26" fill="var(--panel)" />
        <rect
          x="150.75"
          y="26.75"
          width="308.5"
          height="314.5"
          rx="25.25"
          fill="none"
          stroke="var(--border)"
          strokeWidth="1.5"
        />
      </g>

      <text x="176" y="68" className="art-eyebrow">
        SA108 · CAPITAL GAINS
      </text>
      <text x="176" y="108" className="art-big">
        £52,140
      </text>
      <text x="176" y="130" className="art-label">
        disposal proceeds, 2024/25
      </text>

      <g className="art-rows">
        {[
          ['Box 23  Number of disposals', '14'],
          ['Box 25  Allowable costs', '£38,902'],
          ['Box 26  Gains in the year', '£13,238'],
          ['Box 27  Losses brought forward', '£1,910'],
        ].map(([label, value], i) => (
          <g key={label}>
            <text x="176" y={168 + i * 30} className="art-label">
              {label}
            </text>
            <text x="434" y={168 + i * 30} className="art-value" textAnchor="end">
              {value}
            </text>
            <line
              x1="176"
              x2="434"
              y1={178 + i * 30}
              y2={178 + i * 30}
              stroke="var(--border)"
              strokeWidth="1"
            />
          </g>
        ))}
      </g>

      <rect x="164" y="282" width="282" height="42" rx="15" fill="var(--coral-soft)" />
      <text x="182" y="309" className="art-label art-label-strong">
        Capital gains tax due
      </text>
      <text x="428" y="309" className="art-total" textAnchor="end">
        £1,207.60
      </text>

      {/* Section 104 pool chart, tucked behind the card's left edge. */}
      <g filter="url(#cardShadow)" className="hero-float hero-float-a">
        <rect x="10" y="236" width="164" height="150" rx="22" fill="var(--panel)" />
        <rect
          x="10.75"
          y="236.75"
          width="162.5"
          height="148.5"
          rx="21.25"
          fill="none"
          stroke="var(--border)"
          strokeWidth="1.5"
        />
        <text x="30" y="264" className="art-eyebrow">
          SECTION 104 POOL
        </text>
        {[24, 40, 32, 55, 68, 84].map((h, i) => (
          <rect
            key={i}
            x={30 + i * 21}
            y={366 - h}
            width="13"
            height={h}
            rx="6"
            fill={i === 5 ? 'var(--coral)' : 'url(#barFill)'}
          />
        ))}
      </g>

      {/* "Everything reconciled" chip, over the card's top-right corner. */}
      <g filter="url(#chipShadow)" className="hero-float hero-float-b">
        <rect x="250" y="4" width="212" height="46" rx="23" fill="var(--panel)" />
        <circle cx="278" cy="27" r="9" fill="var(--mint-soft)" />
        <path
          d="M274 27.2l2.8 2.9 5.4-5.8"
          fill="none"
          stroke="var(--mint)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <text x="296" y="32" className="art-chip">
          30-day rule applied
        </text>
      </g>

      {/* Allowance chip, over the card's bottom-right corner. */}
      <g filter="url(#chipShadow)" className="hero-float hero-float-c">
        <rect x="278" y="326" width="184" height="46" rx="23" fill="var(--panel)" />
        <circle cx="306" cy="349" r="8" fill="none" stroke="var(--coral-soft)" strokeWidth="4" />
        <path
          d="M306 341a8 8 0 0 1 6.9 12"
          fill="none"
          stroke="var(--coral)"
          strokeWidth="4"
          strokeLinecap="round"
        />
        <text x="324" y="354" className="art-chip">
          £3,000 allowance
        </text>
      </g>
    </svg>
  )
}

const ICONS = {
  upload: (
    <>
      <path d="M4 15.5V19a1.5 1.5 0 0 0 1.5 1.5h13A1.5 1.5 0 0 0 20 19v-3.5" />
      <path d="M12 15.5V3.8" />
      <path d="m7.6 8.2 4.4-4.4 4.4 4.4" />
    </>
  ),
  match: (
    <>
      <circle cx="9" cy="9" r="5.2" />
      <circle cx="15" cy="15" r="5.2" />
      <path d="m10.4 13.6 3.2-3.2" />
    </>
  ),
  planner: (
    <>
      <rect x="3.4" y="4.8" width="17.2" height="15.8" rx="3" />
      <path d="M3.4 9.6h17.2M8.4 3v3.4M15.6 3v3.4" />
      <path d="m9 15.2 2.4 2.2 4-4.6" />
    </>
  ),
  explain: (
    <>
      <path d="M5 3.6h9.2L19 8.4v12a1.4 1.4 0 0 1-1.4 1.4H5a1.4 1.4 0 0 1-1.4-1.4V5A1.4 1.4 0 0 1 5 3.6Z" />
      <path d="M13.8 3.8v4.8h4.8" />
      <path d="M7.4 13h8M7.4 17h5.2" />
    </>
  ),
  lock: (
    <>
      <rect x="4.4" y="10.4" width="15.2" height="10.4" rx="3" />
      <path d="M8 10.2V7.8a4 4 0 0 1 8 0v2.4" />
      <path d="M12 14.6v2.2" />
    </>
  ),
} as const

export type IconName = keyof typeof ICONS

export function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className="feat-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICONS[name]}
    </svg>
  )
}
