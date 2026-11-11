---
name: Garment Operations Engine
colors:
  surface: '#f8f9fa'
  surface-dim: '#d9dadb'
  surface-bright: '#f8f9fa'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f5'
  surface-container: '#edeeef'
  surface-container-high: '#e7e8e9'
  surface-container-highest: '#e1e3e4'
  on-surface: '#191c1d'
  on-surface-variant: '#3e4947'
  inverse-surface: '#2e3132'
  inverse-on-surface: '#f0f1f2'
  outline: '#6e7977'
  outline-variant: '#bdc9c6'
  surface-tint: '#006a63'
  primary: '#005c55'
  on-primary: '#ffffff'
  primary-container: '#0f766e'
  on-primary-container: '#a3faef'
  inverse-primary: '#80d5cb'
  secondary: '#515f74'
  on-secondary: '#ffffff'
  secondary-container: '#d5e3fc'
  on-secondary-container: '#57657a'
  tertiary: '#7f4025'
  on-tertiary: '#ffffff'
  tertiary-container: '#9c573a'
  on-tertiary-container: '#ffe5db'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#9cf2e8'
  primary-fixed-dim: '#80d5cb'
  on-primary-fixed: '#00201d'
  on-primary-fixed-variant: '#00504a'
  secondary-fixed: '#d5e3fc'
  secondary-fixed-dim: '#b9c7df'
  on-secondary-fixed: '#0d1c2e'
  on-secondary-fixed-variant: '#3a485b'
  tertiary-fixed: '#ffdbce'
  tertiary-fixed-dim: '#ffb598'
  on-tertiary-fixed: '#370e00'
  on-tertiary-fixed-variant: '#72361b'
  background: '#f8f9fa'
  on-background: '#191c1d'
  surface-variant: '#e1e3e4'
typography:
  headline-xl:
    fontFamily: Be Vietnam Pro
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Be Vietnam Pro
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Be Vietnam Pro
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Be Vietnam Pro
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Be Vietnam Pro
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Be Vietnam Pro
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Be Vietnam Pro
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: Be Vietnam Pro
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-md:
    fontFamily: Be Vietnam Pro
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: Be Vietnam Pro
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.02em
  numeric-metric-lg:
    fontFamily: JetBrains Mono
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.03em
  numeric-metric-md:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.02em
  numeric-table:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  gutter-compact: 0.5rem
  margin: 1.5rem
  margin-mobile: 0.75rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

This design system is tailored specifically for high-intensity, metric-critical industrial environments—specifically garment line tracking, production forecasting, and floor management. The brand identity represents precision, calm focus, and operational authority.

The audience consists of production floor managers, industrial engineers (IEs), line supervisors, and operations directors who work under shifting industrial lighting and manage dense data across shifts. The UI evokes reliability, swift legibility, and zero cognitive friction.

### Design Movement: Pragmatic Industrial Minimalism
The style rejects decorative gradients, playful visual metaphors, blurred glass, and whimsical graphics. Instead, it adheres to pure utilitarian discipline:
- **High-contrast hierarchy:** Dark, crisp typography over very light, cool-neutral structural backdrops.
- **Physical containment:** Data and workflows live inside structured white cards defined by precise 1px borders.
- **Data density without clutter:** Rhythmic whitespace, strict tabular alignments, and unambiguous color semantics that inform immediate shop-floor interventions.

## Colors

The color system delivers strict legibility under factory-floor conditions, avoiding visual fatigue during extended shifts.

### Palette Architecture
- **Primary (`#0f766e` - Deep Industrial Teal):** Serves as the primary operational anchor for primary actions, selected states, and active telemetry toggles. It conveys institutional authority without the cold sterility of generic enterprise blue. For hover and active states, use `#115e59` and `#134e4a`.
- **Secondary (`#475569` - Slate):** Anchors secondary actions, table headers, column divisions, and secondary controls.
- **Neutral Canvas (`#f8f9fa` with `#f1f5f9` panels):** Provides a clean, glare-free backdrop that allows pure white data containers to stand out with clear boundaries.
- **Card & Surface (`#ffffff`):** All actionable panels, inspection tables, and metric cards sit on pure white surfaces to maximize contrast.
- **Borders & Dividers (`#e2e8f0` to `#cbd5e1`):** Precise 1px borders delineate layout cells, replacing heavy dropshadows.

### Operational Semantic Status Colors
Status colors are reserved exclusively for line performance, output targets, and risk indicators:
- **Target Achieved / Positive Delta (`#16a34a`):** For yield >= 100%, line balancing within tolerance, and positive pace. Paired with background `#f0fdf4` and border `#bbf7d0`.
- **Target Missed / Bottleneck Alert (`#dc2626`):** For critical downtimes, defective lots, and falling cycle times. Paired with background `#fef2f2` and border `#fecaca`.
- **Caution / At Risk (`#d97706`):** For sewing pace variances between 85%–95%. Paired with background `#fffbeb` and border `#fde68a`.
- **Neutral Metric (`#64748b`):** For planned targets, baseline standard allowed minutes (SAM), and static parameters.

## Typography

The typography stack solves two mission-critical needs: pristine Vietnamese diacritic rendering and instant, error-free scanning of production figures.

### Font Selections
- **Primary Body & Interface:** `Be Vietnam Pro` was built specifically for Vietnamese typography. It eliminates accent clipping, baseline shift defects, and awkward tone-mark collisions, maintaining balanced vertical proportions across dense tables and shift reports.
- **Metrics & Tabular Telemetry:** `JetBrains Mono` handles all numerical operations, cycle counters, Standard Allowed Minutes (SAM), pieces-per-hour, and line efficiency percentages. Monospaced character widths guarantee numbers align perfectly along vertical decimal axes without shifting as figures update in real-time.

### Numerical Typography Rules
- Enable `font-feature-settings: "tnum" on, "zero" on` for tabular displays across all numerical representations.
- Negative deltas and downward forecast trends must always pair a mathematical sign (`-`) with their metric to avoid ambiguity for red/green color-blind operators.
- Line headers in data grids use `label-sm` with subtle uppercase tracking to distinguish column definitions from live data values.

## Layout & Spacing

The layout philosophy uses a dense 12-column fluid grid built for shop-floor displays, wallboards, industrial tablets, and production dispatch consoles.

### Spatial Rhythm
- Base scale: 4px step architecture (`0.25rem`, `0.5rem`, `0.75rem`, `1rem`, `1.5rem`).
- Internal card padding defaults strictly to `space-lg` (16px) for standard modules and `space-md` (12px) for high-density monitor stations.
- Gap allocations between operational cards default to `gutter` (16px) to maintain distinct visual separation on low-angle viewing panels.

### Responsive Breakpoints & Layout Adaptations
- **Desktop / Shop-Floor Terminals (>= 1280px):** 12-column fixed-gutter layout. Multi-line side-by-side analytics, real-time hourly tracking charts, and full assembly runouts.
- **Workstation Tablets (768px - 1279px):** 8-column layout. Metric cards collapse to a 2x2 or 4x1 grid. Left navigation rail collapses to an icon-only strip. Data tables introduce sticky primary columns (e.g., Sewing Line ID / Operator ID).
- **Handheld Terminals (< 768px):** 4-column layout with `margin-mobile` (12px). Heavy data grids convert to vertically stacked shift-card items with swipeable inspection details.

## Elevation & Depth

This design system avoids decorative depth, ambient colored blurs, and skeuomorphic drop shadows. High airborne lint and variable lighting in garment factories wash out subtle shadow gradations.

### Flat Boundary Discipline
Hierarchy is achieved through strict border containment and contrast:
- **Base Level (Canvas):** Tone `#f8f9fa`. No border, non-interactive foundation.
- **Tier 1 (Surface Cards & Toolbars):** `#ffffff` surface with a crisp `1px solid #e2e8f0` border. Zero box-shadow in default state.
- **Tier 2 (Popovers, Flyout Modals, Filter Drawers):** `#ffffff` surface with a `1px solid #cbd5e1` boundary accompanied by a functional shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.06)`.
- **Hover/Interactive Surface Highlight:** On interactive rows or selectable cards, transition the border from `#e2e8f0` to `#0f766e` with an inset micro-border or 1px outline. Do not elevate with oversized shadows.

## Shapes

The design system uses structured, compact corner radii (`roundedness: 1`). Soft, rounded geometry (`0.25rem` / 4px base; `rounded-md` / 6px; `rounded-lg` / 8px for outer card containers) maintains an efficient, industrial feel.

### Geometric Rules
- **Container Cards & Dialogs:** Maximum border radius of `6px` (`0.375rem`) to `8px` (`0.5rem`). Tight radii preserve inner usable area for dense metrics and high-column-count data tables.
- **Form Controls & Action Buttons:** `4px` (`0.25rem`) to match standard tactile control paradigms.
- **Status Badges & Indicator Dots:** `4px` (`0.25rem`) for square-cornered tags or pure `9999px` strictly for single-glyph/dot status beacons. Never use pill-shaped pills for operational buttons.

## Components

### Buttons
- **Primary:** Background `#0f766e`, text `#ffffff`, border none, radius `4px`, font `label-lg`. Hover: `#115e59`. Active: `#134e4a`. Focus: `2px solid #0f766e` with 2px offset.
- **Secondary:** Background `#ffffff`, text `#334155`, border `1px solid #cbd5e1`, radius `4px`. Hover: `#f8f9fa`, border `#94a3b8`.
- **Destructive:** Background `#dc2626`, text `#ffffff`, radius `4px`. Used only for stopping lines, rejecting lots, or voiding production orders.
- **Sizes:** Compact (32px height for dense data bars), Default (38px height for standard admin view), Touch (44px height for tablet kiosk interaction).

### Metric Cards (KPI Displays)
- Structural wrapper: `#ffffff`, border `1px solid #e2e8f0`, radius `6px`, padding `16px`.
- Structure:
  1. Top Row: Metric Label (`label-md` in `#64748b`) paired with line identifier or shift badge.
  2. Center Value: Numerical readout (`numeric-metric-lg` in `#0f172a`, mono font).
  3. Bottom Row: Target comparison trend badge (e.g., `+4.2% vs Kế hoạch` with green text `#16a34a` and light green container `#f0fdf4`).

### Data Tables (Line Balancing & Output Tracking)
- **Header:** Background `#f1f5f9`, border-bottom `1px solid #cbd5e1`, text `#475569`, font `label-sm`, text-transform uppercase.
- **Row Styling:** Alternating or plain white with `1px solid #f1f5f9` bottom borders. Row height: 40px (compact floor view).
- **Hover Row:** `#f8fafc` with subtle left border accent `#0f766e`.
- **Numbers:** Right-aligned, `JetBrains Mono` (`numeric-table`). Aligns decimal points for sewing cycle times, actual output, and target deviations.

### Status Chips & Badges
- Compact padding: 2px 8px, font `label-sm`, radius `4px`.
- **On Target (Đạt):** Background `#f0fdf4`, text `#15803d`, border `1px solid #bbf7d0`.
- **Bottleneck (Nghẽn Chuyền):** Background `#fef2f2`, text `#b91c1c`, border `1px solid #fecaca`.
- **Pending/Idle (Chờ Hàng):** Background `#f8fafc`, text `#475569`, border `1px solid #e2e8f0`.

### Form Inputs & Selectors
- Background `#ffffff`, border `1px solid #cbd5e1`, radius `4px`, height `36px`, padding `0 12px`, text `body-md` (`#0f172a`).
- Focus state: Border `#0f766e`, box-shadow `0 0 0 1px #0f766e` (zero blur glow).
- Disabled state: Background `#f1f5f9`, text `#94a3b8`, border `#e2e8f0`.

### Checkboxes & Radios
- Size: 18x18px for fast touch targeting. Border: `1.5px solid #64748b`.
- Checked state: Background `#0f766e`, border-color `#0f766e`, tick glyph pure white.

### Specialized Line Balance Progress Bars
- Background track `#e2e8f0`, height `8px`, radius `2px`.
- Bar fill: Uses semantic colors (`#16a34a` when efficiency >= 90%, `#d97706` for 75-89%, `#dc2626` when < 75%). A thin vertical tick indicates the takt time/target line.