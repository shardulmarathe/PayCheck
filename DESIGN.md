# Design System — SureShop

> Private security room. Cold blue-black, near-white text, one signal red that only ever marks a trick or money lost. The guard is never shown; only its catches.

**Read this whole file before any visual or UI change.** If a request conflicts with this file, follow this file and flag the conflict in your PR description. Figma is the visual source of truth: file `z5f7baVyPevXJte68oBCjV`, page `12:2` "Showcase v3: clear + 3D" (frames `17:553` 01 Demo, `16:2` 01b Replay 2, `17:70` 02 Benchmarks, `18:2` 03 Design process, `18:60` 04 Future, `18:61` M Motion notes, `18:159` T Tokens, `23:10` 05 Table card, and the `N — Navigation + transitions` storyboard). Where this file and Figma disagree on **motion**, this file wins (see Decision log, 2026-10-17). Where they disagree on **color or type values**, the T Tokens frame wins. Fix this file to match it.

## Product context

- **What this is:** SureShop is a small, fast guard model for AI shopping agents. It reads every page and cart before the agent pays, then blocks or steers around checkout tricks: pre-ticked add-ons, popup upsells, hidden fees, copycat stores, listing injection.
- **Who it's for:** Primarily LA AI Hacks judges, who rank from memory using the title, their own notes and the Devpost description. Secondarily, teams building shopping agents.
- **Project type:** Static showcase site (Next.js App Router + Tailwind + Framer Motion + React Three Fiber, deployed on Vercel). Every demo is a recording. Nothing runs live.
- **The one thing judges must remember:** the catch moment. The page dims, red corner brackets lock onto the trick line, a `[N] ms` readout appears and the trick is quoted. Every other design decision supports that moment.

## Art direction: Private security room

- **Mood:** A quiet, dark monitoring room at night. Still until something happens. Expensive, precise, slightly cinematic. It's never a hacker cliché: no green terminal text, no matrix rain, no glitch effects.
- **Base:** Cold blue-black (`bg #0A0C0F`) with near-white text (`text #EEF1F5`). Surfaces step up in tiny, cool increments. Hairlines do the structure, not boxes or shadows.
- **Signal red `#FF453A` is the ONLY accent**, and it has exactly three meanings:
  | Red treatment | Meaning |
  |---|---|
  | **Solid red fill** (text in `bg` color) | Money lost: the damaged receipt line, the over-budget total, the "Unguarded: −$X" counter |
  | **Thin 1.5 px corner brackets + slight glow** | A catch, *at the moment it happens*. Glow fades and the brackets **settle to near-white `#EEF1F5`** |
  | **Bracket stroke style** | **Dashed `[4, 3]` = scam** (copycat, injection, fake verification). **Solid = upsell** (add-on, pre-ticked box, drip fee) |
- **Tab underline:** the 2 px red tab underline is the single UI use of red, per the T Tokens frame. It's chrome, not a claim, and it's the only exception.
- **The guard is never shown.** No mascot, shield icon, robot, eye or character. We only show what it caught.
- **Our own claims and points are never red.** Catch rate, the SureShop dot on charts, "Guarded: −$0.00", the headline number: all white or near-white. Red belongs to the trick and the loss, never to us.
- **No gradients, no frosted glass, no glassmorphism, no backdrop-blur panels.** Flat fills only. The only soft edges allowed are the panel drop shadows and the blurred floor plane under the replay panels (see Motion).

## Color tokens (exact, from Figma T Tokens `18:159`)

| Token | Hex | Role |
|---|---|---|
| `--bg` | `#0A0C0F` | Page background, cold blue-black |
| `--surface-1` | `#11141A` | Browser frames, code blocks, kiosk body material |
| `--surface-2` | `#171B22` | Raised: chrome bars, popups |
| `--surface-3` | `#1E232B` | Placeholders inside recordings |
| `--hairline` | `#232932` | Dividers, grid lines, 1 px |
| `--hairline-strong` | `#323A45` | Loop, chart tracks, popup edge, kiosk edges |
| `--text` | `#EEF1F5` | Primary text · 17.3:1 on bg |
| `--text-2` | `#9AA3AE` | Secondary text · 7.7:1 on bg |
| `--text-3` | `#7A838F` | **Restricted:** non-reading decoration only (axis ticks next to a labelled value, disabled states). Never for sentences, captions or labels someone has to read. Use `--text-2` for those. |
| `--signal-red` | `#FF453A` | The trick / money lost. 5.75:1 on bg, 5.1:1 on surface-2. Tuned from #FF3B30 for AA |

**Readable grays rule:** any text a person is meant to read uses `#9AA3AE` or lighter. `#7A838F` fails our bar for captions on projectors.

**Glow (red only, catch moment only):** `filter: drop-shadow(0 0 8px rgb(255 69 58 / .45))` (Figma: x 0 · y 0 · blur 16 · #FF453A @ 45%). It rises over 300 ms at the catch, holds, then fades over 600 ms as the brackets settle to near-white.

**Lines:** hairline 1 px `#232932` · strong 1 px `#323A45` · bracket 1.5 px red → near-white · tab underline 2 px red.
**Radius:** 0 for rules and charts · 2 for buttons, inputs and swatches · 4 for browser frames and code blocks. No pills, no bubble radius.
**Dark only.** There is no light mode.

## Typography (IBM Plex Sans + IBM Plex Mono)

Load with `next/font/google` (`IBM_Plex_Sans` weights 300/400, `IBM_Plex_Mono` weights 300/400/500), `display: 'swap'`. No other families. No system-ui.

| Role | Family / weight | Size / line-height · tracking | Use |
|---|---|---|---|
| Display | Plex Sans Light | 76/82 · −3% | Hero tagline only |
| H1 | Plex Sans Light | 56/62 · −3% | Section openers (Benchmarks, Design process, Future) |
| H2 | Plex Sans Light | 48/56 · −2% | Sub-section heads |
| H3 | Plex Sans Light | 32/40 · −2% | Errand titles ("AA batteries, 12-pack, under $15") |
| Title | Plex Sans Light | 22/30 · −1% | List items, card titles |
| Body L | Plex Sans Regular | 18/30 | Hero sub-copy, lead paragraphs |
| Body | Plex Sans Regular | 16/27 | Paragraphs |
| Number XL | Plex Mono Light | 56/64 · −4% · tabular | Totals, counters ($14.48, −$0.00) |
| Number | Plex Mono Regular | 13/18 · tabular | Prices, `[N] ms`, table cells |
| Label | Plex Mono Regular | 13 · caps · +6% · `#9AA3AE` | `BLOCKED · UPSELL`, eyebrows |
| Micro | Plex Mono Regular | 12 · caps · +4% · `#9AA3AE` | Captions, chart axes. **The minimum size** |

- **Minimum text size is 12 px.** Nothing smaller, including chart ticks and footer.
- **Every number is `font-variant-numeric: tabular-nums`.** Counters must not jitter while they count.
- Sans carries the **voice** (claims, sentences). Mono carries the **instrument** (numbers, readouts, labels, URLs, timings).
- Sentence case for headings and buttons. Caps only in mono Label/Micro roles.

## Spacing and layout

- 4 px base: 4, 8, 12, 16, 24, 32, 48, 64, 96, 120.
- Page margin 120 · content width 1200 · section gap 120–160 · column gap 48 (desktop 1440). Use `clamp()` to scale margins down to 20 px on mobile.
- Only the hero gets `min-height: 100dvh`. Every other section sizes to its content plus section padding. Never `h-screen`, and no `justify-content: center` on full-width sections.

## Copy rules

- **Name:** `SureShop` (one word, capital S twice). Never "Sure Shop", "SURESHOP" or "sureshop" in UI.
- **Tagline:** "Your agent shops. We check the checkout." Verbatim, everywhere: hero, Devpost first line, table card.
- **Headline number slot:** "Catches [X]% of checkout tricks." It's the same sentence on the hero, the Benchmarks H1 and the table card. `[X]` stays a visible slot until the real frozen-test number lands; never invent one.
- **Baseline line:** never say "beats". Say "level with" or "within [N] points of" the baseline model, and only with numbers from a checked eval. No cost-ratio phrase.
- **Never show "example data" labels** to judges. If a block has no real data at freeze, **hide the whole block** (render nothing, collapse its space). There are no placeholders in production.
- **Latency:** show the measured value. Below 1000 ms show `[N] ms` (integer, e.g. `412 ms`). At 1000 ms and above show seconds with one decimal (`1.3 s`). Never hard-code a number in markup; it comes from the run data.
- **Footer, verbatim:** "Recorded demos. Nothing on this site runs live."
- **Money:** always two decimals and a real minus sign (`−$9.99`, U+2212). "Unguarded: −$X" is red; "Guarded: −$0.00" is white.
- **Trick quotes:** quote the page's exact words in mono, e.g. `"By continuing, Battery Care+ ($9.99) is added to your order."`
- No exclamation marks, no emoji, no "revolutionary/seamless/unleash". No sponsor or model-vendor logos.

## Navigation and transition architecture

The site is **one continuous shot**. The hero is the 3D checkout kiosk, treated as *the computer the story plays on*. After the intro, visitors can **scroll the whole story top to bottom or click a tab**, and either way, every move between sections is a connected camera move, never a page cut.

### Tech spine (buildable in a hackathon)

```
<SmoothScroll>            // client: Lenis, owns the one scroll position
  <MotionConfig reducedMotion="user" transition={{ ease: EASE, duration: 0.8 }}>
    <IntroProvider>       // phase: 'loader' | 'catch' | 'pullback' | 'done'
      <NavProvider>       // activeTab, isGliding, glideTo(id)
        <TabBar/> <ProgressHairline/>
        <Hero/> <Replay/> <Benchmarks/> <DesignProcess/> <Future/> <Footer/>
```

- **One scroll engine:** Lenis (`lerp: 0.09`, `smoothWheel: true`, `syncTouch: false` so touch stays native), driven from one `requestAnimationFrame`. Framer `useScroll()` reads `window` scroll, which Lenis drives, so every scroll-linked transform shares that position. No second scroll library, no ScrollTrigger, no CSS `scroll-behavior: smooth`.
- **Sections** carry `id` = `demo`, `benchmarks`, `design-process`, `future` and `data-tab` for the active-tab observer.
- **3D:** the kiosk is a client-only component loaded with `next/dynamic(..., { ssr: false })`. The kiosk screen is DOM via drei `<Html transform>` on the screen plane, so the catch, brackets and quote are real HTML. That lets the loader mark target an exact rect with `getBoundingClientRect()`. A static poster image (same angle) renders until the canvas is ready.

### Intro (first visit per session; any wheel, key, click or touch skips to the settled state)

| t (approx.) | Beat |
|---|---|
| 0 – 0.9 s | **Loader.** `bg` only. The `SureShop` wordmark (Plex Sans Light) and the red corner-bracket mark (four 1.5 px corners) sit centered. A near-white progress hairline runs along the top. |
| 0.9 – 2.0 s | **Bracket mark flies to the kiosk.** The kiosk poster/canvas is already behind the loader. The mark FLIPs from its loader rect to the **exact rect of the trick line on the kiosk screen** (`getBoundingClientRect` of `[data-trick-line]`) over 1.1 s ease-in-out, while the loader `bg` fades out over 250 ms. No fade between loader and hero: the mark *is* the hand-off. |
| 2.0 – 4.4 s | **The catch plays on the kiosk screen** (the one beat allowed to run long). The page dims to 28% (300 ms). A near-white scan line sweeps the screen (900 ms). As it crosses the trick line, the four brackets close on it (250 ms), the red glow rises (300 ms), the `[N] ms` readout counts up in red mono, and the trick sentence is quoted below in mono. It holds for 600 ms, then the glow fades (600 ms), the brackets settle to near-white, and the label reads `Blocked · [N] ms` in `text-2`. |
| 4.4 – 5.5 s | **Camera pull-back + tabs.** The R3F camera dollies back (z ≈ 2.2 → 4.0) and drifts right so the kiosk lands in its Figma position (right half, `17:553`), over 1.1 s ease-in-out. The dim lifts. The tab bar fades in (opacity 0→1, y −8→0, 250 ms) once the pull-back lands. Hero copy enters: eyebrow, tagline, headline number, sub-copy (800 ms, stagger 60 ms). |
| ≥ 5.5 s | `phase = 'done'`. Scroll and tabs unlock. `sessionStorage.sureshopIntro = 1`, so repeat visits start settled. |

Lenis is `stop()`ed during the intro and `start()`ed at `done` or on skip.

### After the intro: both full scroll and tabs work

- **Tab bar:** slim, sticky, `bg` at 100% (no blur), with a 1 px `hairline` bottom. `SureShop` sits left; tabs **Demo · Benchmarks · Design process · Future improvements** sit right (Figma labels; "Future" is allowed on screens under 640 px). Its height is the `NAV_H` constant (56 px).
- **Tab click = glide:** `lenis.scrollTo('#id', { offset: -NAV_H, duration: 1.1, easing: easeInOutCubic, lock: true, onComplete })`. While gliding, `isGliding = true`:
  - **Entrance reveals are suppressed.** Sections passed on the way are set straight to their settled state, so nothing flashes past at speed.
  - **Scroll-linked connectors** (below) are tied to scroll position, so they scrub naturally during the glide. That is the camera move.
  - The **active tab switches immediately to the destination**, so the underline slides once instead of stepping through every tab.
  - On `onComplete`, `isGliding = false` and the **destination section builds in** (its section entrance: 800 ms, stagger 60 ms).
  - Update the hash with `history.replaceState`. On load with a hash, skip the intro and jump to the section (no glide).
- **Active tab underline:** a single 2 px red `motion.span` with `layoutId="tab-underline"` that slides between tabs (250 ms, EASE). While scrolling, the active tab comes from which `data-tab` section crosses 40% of the viewport.
- **Scroll progress hairline:** 1 px, `#EEF1F5` at 60% opacity, fixed to the very top above the tab bar, `scaleX` from `useScroll().scrollYProgress` (transform-origin left). It's the slim navigation cue.
- **Keyboard:** tabs are real `<a href="#id">` links. Focus rings use a 1 px near-white outline with 2 px offset. Never red.

### Section-to-section connecting moves (one continuous shot)

Each boundary has one element that **carries across**, so the eye never loses its place. All of these are scroll-linked (`useScroll({ target, offset })` + `useTransform`) unless noted. Each is one fixed-position "carrier" element that maps between two measured rects (FLIP by scroll progress), then hands off to the real element with a 1-frame swap. No shared-element routing, so it's buildable.

1. **Loader → Hero:** the red bracket mark becomes the kiosk's catch brackets (FLIP, see Intro).
2. **Hero → Replay 1 ("the kiosk screen becomes the replay"):** as the hero scrolls out (`offset: ['start start', 'end start']`), the kiosk rotates about 20° on y (scroll-driven, never on its own) and **the kiosk screen card (DOM) travels and scales into the "With guard" panel**. Its bracketed trick line is the same line, in the same position, inside the guarded panel's popup. The "Without guard" panel slides in from the left at `rotateY(8deg)`. Both panels flatten to `rotateY(0)` as they reach viewport center.
3. **Replay 1 → Replay 2 (in-section switcher, not a tab):** the browser chrome and URL bar **hold still**. Only the content crossfades (250 ms). Then the copycat letter flip plays: `brightcell.shop`, the `l` flips to `1` over 400 ms, and a **dashed** red bracket snaps around just those characters.
4. **Replay → Benchmarks ("the counter becomes the headline number"):** the receipt prints (lines 120 ms apart), then the counters land: "Unguarded: −$X" (red fill) and "Guarded: −$0.00" (white). As Benchmarks enters, the **red counter fades out in place** (red never travels into our claims). The **white guarded counter is the carrier**: it rises into the Benchmarks H1 slot and its digits roll (tabular, 600 ms) from `$0.00` to `[X]%`, completing "Catches [X]% of checkout tricks."
5. **Benchmarks headline → chart:** the hairline under the H1 extends full width and becomes the chart's 100% gridline. Gridlines draw left→right (stagger 60 ms). The SureShop dot (white) appears at its point, then the dashed connector draws from the baseline dot to ours (900 ms, `pathLength`).
6. **Benchmarks → Design process ("the dot becomes the loop"):** the white ring around the SureShop dot is the carrier. It scales up and stretches into the Design-process loop ellipse (`hairline-strong`, 1 px). The four loop nodes then light in order 01 → 04 (stagger 120 ms), and a single near-white tick travels once around the loop. It isn't continuous: nothing moves when idle.
7. **Design process → Future ("the miss feeds the next lesson"):** node 04, "Misses go back into training", drops a near-white dot that runs down a vertical hairline into the `01` index of the Future list. Each row's top hairline draws left→right (stagger 60 ms), then the row text enters.
8. **Future → Footer:** no carrier. The last hairline becomes the footer rule. The footer is static.

Tab glides pass through these same connectors (they're tied to scroll), so a click from Demo to Future is the whole story at 1.1 s speed, then the destination builds in.

### Reduced motion and fallbacks

- `prefers-reduced-motion: reduce` → no intro (settled hero, brackets already near-white, label showing), no rotation, tilt, sweep, count, roll or carrier travel. Panels render flat with damage fills in place. Tab clicks jump (`lenis.scrollTo(..., { immediate: true })`). Durations collapse to 0.01 ms.
- No WebGL or slow device (`navigator.hardwareConcurrency <= 4` or canvas creation fails) → poster image of the kiosk with the same DOM screen overlay. The catch still plays.
- Touch: Lenis off for touch (native momentum). Connectors still scrub from native scroll.

## Motion budget

| Token | Value | Use |
|---|---|---|
| `EASE` | `cubic-bezier(.2,.8,.2,1)` (Framer `[0.2, 0.8, 0.2, 1]`) | **Everything**, except the two glides below |
| `EASE_GLIDE` | ease-in-out (`easeInOutCubic`) | Tab glide and the intro mark flight/pull-back only, because a camera move needs to accelerate and land |
| `HOVER` | 150 ms | Hover, press, focus |
| `PANEL` | 250 ms | Popups, switcher crossfade, tab underline, tab bar fade-in |
| `ENTER` | 700–900 ms (default 800) | Section entrances |
| `STAGGER` | 60 ms | Children inside an entrance |
| `TRIGGER` | element top at 85% of viewport (`useInView({ margin: '0px 0px -15% 0px', once: true })`) | Entrance start |
| `GLIDE` | 1.1 s | Tab glide, loader mark flight, camera pull-back |
| `CATCH` | ~2.4 s total, slow and cinematic | **The only beat allowed to exceed 1.1 s** |
| Receipt print | 120 ms per line | Thermal-printer feel |
| Letter flip | 400 ms | Copycat `l`→`1` |
| Glow | rise 300 ms / fade 600 ms | Catch only |

- **Panels tilt in depth:** the parent gets `perspective: 1600px`. The left panel starts at `rotateY(8deg)`, the right at `rotateY(-8deg)` (inner edges away), and both ease to `rotateY(0)` as they reach viewport center (scroll-linked). Shadows tighten as they flatten (`0 40px 80px rgba(0,0,0,.55), 0 8px 16px rgba(0,0,0,.45)`), with a blurred black floor plane (28 px blur) under each.
- **Animate only `transform` and `opacity`** (plus `filter` for the catch glow and `pathLength` for SVG draws). Never animate layout properties.
- **Nothing moves when idle.** No loops, pulses or ambient drift after the intro.
- `prefers-reduced-motion` collapses all durations (see above). Use `useReducedMotion()` in any component with custom timing.
- **3D is isolated in client components** (`'use client'`, dynamic import, `ssr:false`). Server components render static layout only.
- **Never mix GSAP and Framer Motion in the same component.** The default stack is Lenis + Framer, and GSAP should not be needed. If one isolated component truly needs it, it owns that component entirely.

## Banned list (never ship)

- Gradients of any kind: backgrounds, text, buttons, borders, shader "silk" waves
- Glass: frosted panels, `backdrop-filter: blur`, glassmorphism cards
- Parallax on data (charts, tables, receipts, numbers move only with the page)
- A floating or bobbing hero. The kiosk moves only with scroll or during the intro.
- Per-letter or per-word text reveals, text scramble/scatter, typewriter headings (receipt lines typing out is the one exception, line by line)
- Extra accent colors (no green "success", no blue links, no amber). Red is the only accent.
- Red on our own claims, catch rates, the SureShop chart dot, the guard or decoration
- "Example data" labels or placeholder numbers in production
- Sponsor branding, model-vendor logos, hackathon badges in the UI
- Shield, lock or robot icons representing the guard, and mascots
- Emoji, pill buttons, bubble radius, 3-column icon-in-circle feature grids
- Auto-playing carousels, confetti, particle storms, custom cursors
- Text smaller than 12 px, or reading text darker than `#9AA3AE`

## Component decisions

| Component / technique | Decision | Notes |
|---|---|---|
| Lenis smooth scroll | ✅ Allowed | The one scroll engine. `lerp 0.09`, native on touch |
| Framer Motion (`useScroll`, `useTransform`, `useInView`, `layoutId`, `MotionConfig`) | ✅ Allowed | The default motion library |
| React Three Fiber + drei (`<Html transform>`, `PerspectiveCamera`) | ✅ Allowed | Kiosk only. `MeshStandardMaterial #11141A`, roughness 0.8, 1 px `#323A45` edges, one `#EEF1F5` rim light upper-left |
| SVG `pathLength` draws (chart connector, gridlines, loop) | ✅ Allowed | |
| Custom tabular digit roll (counter → headline) | ✅ Allowed | Build it in-house (about 40 lines). No library |
| FLIP carrier elements (measured rects + scroll progress) | ✅ Allowed | The connecting moves |
| Subtle static noise texture | ⚠️ Conditional | Behind the kiosk only, ≤ 4% opacity, static (no animated grain), never over data |
| GSAP / ScrollTrigger | ⚠️ Conditional | Only if Framer can't do a specific beat, and only in its own component. Never with Lenis-Framer scroll-linked code in the same component |
| `@react-three/postprocessing` (bloom etc.) | ⚠️ Conditional | Skip unless the kiosk looks flat. Glow stays CSS `drop-shadow` on DOM brackets |
| View Transitions API | ❌ Skip | This is a single page; carriers handle continuity |
| React Bits fluid cursor / smooth cursor / splash cursor | ❌ Skip | Custom cursors are banned |
| React Bits text-scatter / split-text / blur-text | ❌ Skip | Per-letter reveals are banned |
| React Bits silk-waves / aurora / any shader background | ❌ Skip | Gradients |
| Glass cards, liquid glass | ❌ Skip | Banned |
| Locomotive Scroll / GSAP ScrollSmoother | ❌ Skip | Lenis is the one engine |
| Scroll snapping (`scroll-snap-type`) | ❌ Skip | Fights Lenis and the glide |
| Spline embeds / Lottie | ❌ Skip | Heavy and off-style. R3F covers 3D |
| Magnetic buttons, tilt-on-hover cards | ❌ Skip | Motion without meaning |

## Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-10-17 | Direction: Private security room | Cold blue-black, near-white, one signal red. It reads as a monitoring room, which fits a guard that watches checkouts. |
| 2026-10-17 | Red means exactly three things: solid = money lost, brackets + glow = catch (settles to white), dashed vs solid = scam vs upsell | One accent with fixed meanings, so judges learn the code in one replay. |
| 2026-10-17 | Our claims are never red; the guard is never shown | Red is the enemy's color. Showing only catches keeps the story about outcomes. |
| 2026-10-17 | Type: IBM Plex Sans + IBM Plex Mono, min 12 px, readable grays `#9AA3AE`+ | Matches Figma T Tokens. Projector-safe. `#7A838F` restricted to non-reading decoration. |
| 2026-10-17 | Hero = the 3D checkout kiosk as "the computer" the story plays on | User direction. The intro plays on its screen, then the camera pulls back. |
| 2026-10-17 | Both full scroll and tabs after the intro | User direction. Tabs glide (1.1 s) through the same scroll-linked connectors, so a click still feels like one shot. |
| 2026-10-17 | Tab change = glide; **supersedes the Figma M frame's ~700 ms "shutter cut"** | A cut breaks the continuous-shot idea. The glide plus build-in on arrival is the connected version. |
| 2026-10-17 | Global ease `cubic-bezier(.2,.8,.2,1)`; **supersedes Figma M frame's `(0.22,1,0.36,1)`, 600–1,200 ms** | Aligns with the motion table adopted from the qtzx/vima research (one curve, 150/250/800 ms tiers). The curves are visually near-identical, and one written value avoids drift. Figma M frame should be updated to match. |
| 2026-10-17 | One scroll engine (Lenis → Framer `useScroll`), no GSAP alongside Framer | Lesson from vima: everything reading one scroll position is why its page moves as one piece. |
| 2026-10-17 | Loader hand-off by FLIPping the bracket mark onto the kiosk trick line | Borrowed from vima's loader-mark-to-hero hand-off. No fade between intro and hero. |
| 2026-10-17 | Counter → headline carrier uses the white guarded counter; the red counter fades in place | Keeps red off our claims while making the replay's payoff become the benchmark number. |
| 2026-10-17 | Hide blocks without real data at freeze; no "example data" labels | Judges rank from memory, and a placeholder label reads as "not done". |
| 2026-10-17 | Latency rendered from data as `ms` (< 1000) or `s` (one decimal) | Figma already uses `[N] ms` slots. No hard-coded latency. |
| 2026-10-17 | `DESIGN.md` is mandatory reading for coding agents before UI changes | Method borrowed from qtzx.dev's repos (every project ships one). It keeps parallel agents consistent. |

## Open questions

- Demo format (laptop, projector or recorded video): on a projector, raise `text-2` usage to `text` for captions and bump Micro to 13 px.
- Final `[X]` and `[N]` land after the frozen-test run. The copy rule above applies.
- Site URL for the table-card QR (after Vercel deploy).
