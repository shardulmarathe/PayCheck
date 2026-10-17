# Design System — SureShop

> Private security room. Cold blue-black, near-white text, one signal red that only ever marks a trick or money lost. The guard is never shown; only its catches.

**Read this whole file before any visual or UI change.** If a request conflicts with this file, follow this file and flag the conflict in your PR description. Figma is the visual source of truth: file `z5f7baVyPevXJte68oBCjV`, page `12:2` "Showcase v3: clear + 3D" (frames `17:553` 01 Demo, `16:2` 01b Replay 2, `17:70` 02 Benchmarks, `18:2` 03 Design process, `18:60` 04 Future, `18:61` M Motion notes, `18:159` T Tokens, `23:10` 05 Table card, and `29:59` N — Navigation + transitions storyboard). Where this file and Figma disagree on **motion**, this file wins (see Decision log, 2026-10-17). Where they disagree on **color or type values**, the T Tokens frame wins. Fix this file to match it.

## Product context

- **What this is:** SureShop is a small, fast guard model for AI shopping agents. It reads every page and cart before the agent pays, then blocks or steers around checkout tricks: pre-ticked add-ons, popup upsells, hidden fees, copycat stores, listing injection.
- **Who it's for:** Primarily LA AI Hacks judges, who rank from memory using the title, their own notes and the Devpost description. Secondarily, teams building shopping agents.
- **Project type:** Static showcase site (Next.js App Router + Tailwind + Framer Motion + React Three Fiber, deployed on Vercel). Every demo is a recording. Nothing runs live.
- **The one thing judges must remember:** the use case and how useful it is. Your shopping agent buys batteries, a sneaky checkout adds $9.99, and SureShop stops it before you pay. The catch moment (calm brackets locking onto the trick line) is the proof. See **Memorability**.

## Art direction: Private security room

- **Mood:** A quiet, dark monitoring room at night. **Confident and calm, not tense.** Still until something happens, and even then precise rather than alarming. Expensive, slightly cinematic. It's never a hacker cliché: no green terminal text, no matrix rain, no glitch effects.
- **Base:** Cold blue-black (`bg #0A0C0F`) with near-white text (`text #EEF1F5`). Surfaces step up in tiny, cool increments. Hairlines do the structure, not boxes or shadows.
- **Signal red `#FF453A` is the ONLY accent**, and it has exactly three meanings:
  | Red treatment | Meaning |
  |---|---|
  | **Solid red fill** (text in `bg` color) | Money lost: the damaged receipt line, the over-budget total, the "Unguarded: −$X" counter |
  | **Thin 1.5 px corner brackets + slight glow** | A catch, *at the moment it happens*. Glow fades and the brackets **settle to near-white `#EEF1F5`** |
  | **Bracket stroke style** | **Dashed `[4, 3]` = scam, something false** (copycat, injection, fake verification, fake urgency, price change at checkout). **Solid = upsell, something that adds money** (add-on, pre-ticked box, drip fee, subscription trap) |
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

**Glow (red only, catch moment only, and quiet):** no glow surge. At most a faint, steady halo `filter: drop-shadow(0 0 6px rgb(255 69 58 / .20))` that's present as the brackets lock and fades over 500 ms as they settle to near-white. (The T Tokens frame's 45% glow is retired for motion; see Decision log.)

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
- **Sonnet line:** comes from the results file (`runs/eval/results.json`), never from a hardcoded "Sonnet-level" or a hardcoded cost. The hero shows **one** slice, chosen by `hero_slice` (default `in_dist`): "Level with the baseline model" only when that slice's `claim` is exactly `"beats"`; otherwise "Within [N] points of the baseline model", and `[N]` is replaced only when that slice has `gap_points`. A 12 px tag under it names the slice: "on familiar pages", "on new attacks", or "on new templates". Benchmarks states every slice in one sentence ("Level with the baseline model on familiar pages, within [N] points on new attacks") and draws that slice's error bars (`ci_low` / `ci_high` per model). Append "at 1/[N] the cost" only when **both** the guard and Sonnet have `cost_per_page_usd`; otherwise leave the cost phrase out. Do not invent the ratio from `cost_per_1k_checks_usd`. A file with `"synthetic": true` is schema only — production hides its scores, claims, gaps, and costs.
- **Never show "example data" labels** to judges. If a block has no real data at freeze, **hide the whole block** (render nothing, collapse its space). There are no placeholders in production.
- **Latency:** show the measured value. Below 1000 ms show `[N] ms` (integer, e.g. `412 ms`). At 1000 ms and above show seconds with one decimal (`1.3 s`). Never hard-code a number in markup; it comes from the run data.
- **Footer, verbatim:** "Recorded demos. Nothing on this site runs live."
- **Money:** always two decimals and a real minus sign (`−$9.99`, U+2212). "Unguarded: −$X" is red; "Guarded: −$0.00" is white.
- **Trick quotes:** quote the page's exact words in mono, e.g. `"By continuing, Battery Care+ ($9.99) is added to your order."`
- No exclamation marks, no emoji, no "revolutionary/seamless/unleash". No sponsor or model-vendor logos.

## Memorability

**Judges must remember the use case and how useful it is.** The catch moment is how we prove it, not the thing itself.

- **The one-glance test:** the first screen after the intro must make the everyday use case unmistakable. *Your shopping agent buys batteries for you. A sneaky checkout adds $9.99. SureShop stops it before you pay.* Someone who looks for three seconds and walks away should be able to repeat that.
- **Use-case line (landing, under the tagline):** "You ask your AI agent to buy batteries. The checkout slips in a $9.99 add-on. SureShop stops it before your agent pays." Plex Sans Regular 20/30, `text`, max width 560. It's in Figma `17:553` (node `26:2`) and on the table card `23:10` (node `26:3`). The `$9.99` must match the recorded replay's add-on price at freeze. If the recording changes, update the line.
- **Landing stays uncluttered:** eyebrow → tagline → use-case line → headline number → one Sonnet claim and its slice tag, with the kiosk on the right. The old sub-line ("A small, fast model reads every page and cart…", `17:601`) is hidden because the use-case line replaces it. Don't add badges, logos or a CTA row to the hero.
- **The replay tells the same story:** same errand (AA batteries, 12-pack, under $15), same store, same agent. Without SureShop the $9.99 add-on goes through and the receipt shows the red line. With it, the agent declines before paying. The counters ("Unguarded: −$X" red, "Guarded: −$0.00" white) are the punchline of that story, and the caption under them says it in words.
- **Everything else is evidence for the use case:** Benchmarks = "it catches most tricks, cheaply"; Design process = "how it learns"; Future = "what it learns next". No section introduces a new story.

## Navigation and transition architecture

**Feel: confident and calm, not tense.** The site is **one continuous 3D-ish space**, and the visitor is a camera moving through it. The checkout kiosk is the anchor of that space: it's the hero during the intro, then it recedes to a small, dim object in the background and **stays there for the whole page**. Scrolling and tab clicks are both a **camera dolly/track through the same space**, never channel switching. No shake, no flicker, no strobe, no surges.

### Tech spine (buildable in a hackathon)

```
<SmoothScroll>            // client: Lenis, owns the one scroll position
  <MotionConfig reducedMotion="user" transition={{ ease: EASE, duration: 0.8 }}>
    <IntroProvider>       // phase: 'loader' | 'catch' | 'pullback' | 'done'
      <NavProvider>       // activeTab, isGliding, glideTo(id)
        <BackgroundKiosk/>   // fixed, z-0, behind all content, persists
        <TabBar/> <ProgressHairline/> <BracketCursor/>   // cursor: desktop only
        <Hero/> <Replay/> <Benchmarks/> <DesignProcess/> <Future/> <Footer/>   // z-10
```

- **One scroll engine:** Lenis (`lerp: 0.09`, `smoothWheel: true`, `syncTouch: false` so touch stays native), driven from one `requestAnimationFrame`. Framer `useScroll()` reads `window` scroll, which Lenis drives, so every scroll-linked transform and the kiosk camera share that position. No second scroll library, no ScrollTrigger, no CSS `scroll-behavior: smooth`.
- **Sections** carry `id` = `demo`, `benchmarks`, `design-process`, `future` and `data-tab` for the active-tab observer.
- **3D:** one R3F `<Canvas>` in a `position: fixed; inset: 0; z-index: 0; pointer-events: none` layer, loaded with `next/dynamic(..., { ssr: false })`. All content sits above it at `z-index: 10`. The kiosk screen is DOM via drei `<Html transform>` on the screen plane, so the catch and brackets are real HTML. That lets the loader mark and the replay lift-off target exact rects with `getBoundingClientRect()`. A static poster image (same angle) renders until the canvas is ready.

### Intro (~4 s; first visit per session; any wheel, key, click or touch skips to the settled state)

| t (approx.) | Beat |
|---|---|
| 0 – 0.7 s | **Loader.** `bg` only. The `SureShop` wordmark (Plex Sans Light) and the red corner-bracket mark (four 1.5 px corners) sit centered. A near-white progress hairline runs along the top. |
| 0.7 – 1.6 s | **Bracket mark travels to the kiosk.** The mark FLIPs from its loader rect to the **exact rect of the trick line on the kiosk screen** (`[data-trick-line]`) over 0.9 s with calm ease-in-out, while the loader `bg` fades out over 250 ms. No fade between loader and hero: the mark *is* the hand-off. |
| 1.6 – 3.0 s | **The catch plays on the kiosk screen: calm and precise.** The rest of the page dims softly to **60%** (400 ms). **One** slow near-white sweep passes down the screen (700 ms), once, with no strobe. As it reaches the trick line, the four brackets **lock in one smooth, precise move** (400 ms, EASE: no overshoot, no bounce, no shake). The `[N] ms` readout fades in beside them (250 ms, no count-up flicker), and the trick sentence is quoted in mono. There's no glow surge: at most a faint, steady red halo (≤ 20% opacity) that fades out as the brackets **settle to near-white** (500 ms). The label reads `Blocked · [N] ms` in `text-2`. |
| 3.0 – 4.0 s | **Camera pull-back.** The dim lifts. The R3F camera dollies back (1.0 s, calm ease-in-out) and the kiosk recedes to its hero position (right half, `17:553`). The tab bar fades in (opacity 0→1, y −8→0, 250 ms) as the pull-back lands. Hero copy enters: eyebrow, tagline, use-case line, headline number (700 ms, stagger 60 ms). |
| ≥ 4.0 s | `phase = 'done'`. Scroll and tabs unlock. `sessionStorage.sureshopIntro = 1`, so repeat visits start settled. |

Lenis is `stop()`ed during the intro and `start()`ed at `done` or on skip.

### The background kiosk (persists after the hero)

- **Receding:** as the hero scrolls out, the kiosk keeps receding until it's a **small, dim, fixed 3D object** at the right of the viewport: about **20–25% of viewport height**, around `right: 6vw; bottom: 12vh`, low contrast (materials at ~35% brightness, edges `hairline` rather than `hairline-strong`, no rim highlight). It stays there for every section after the hero.
- **Never over data or text:** it sits behind content (`z-index: 0`) in the right gutter. Wherever a section's content spans full width (the chart, the replay panels), that section reserves the gutter or the kiosk dims further (to ~20%) while the section is centered. It never takes pointer events.
- **Screen mirrors the current section** (tiny, quiet, near-white on `surface-2`, crossfade 250 ms when `activeTab` changes):
  | Section | Kiosk screen state |
  |---|---|
  | Demo / Replay | The trick line with settled near-white brackets |
  | Benchmarks | A miniature bar: our catch rate as a single white bar on a `hairline` track |
  | Design process | A tiny loop: hairline ellipse with one white dot |
  | Future | Three short stacked hairline rows |
- **The only allowed parallax:** as the camera dollies or tracks through the page, the kiosk shifts slightly (≤ 24 px translate and ≤ 4° rotation.y over the full page, mapped from `scrollYProgress`). Data, text and panels never parallax. The kiosk never moves on its own; idle means still.
- **Mobile < 640 px:** hide the background kiosk after the hero (or show it as a static poster in the hero only). **Reduced motion:** static poster in its settled spot, no parallax, no screen crossfades (screen shows the Demo state).

### After the intro: camera moving through one space (scroll and tabs)

- **Mental model:** sections are laid out along one continuous track around the background kiosk. Scrolling is the camera moving along that track. A tab click is the same camera, moved for you. Nothing cuts, swaps or "changes channel".
- **Tab bar:** slim, sticky, `bg` at 100% (no blur), with a 1 px `hairline` bottom. `SureShop` sits left; tabs **Demo · Benchmarks · Design process · Future improvements** sit right (Figma labels; "Future" is allowed under 640 px). Its height is the `NAV_H` constant (56 px).
- **Tab click = camera glide:** `lenis.scrollTo('#id', { offset: -NAV_H, duration: 1.1, easing: easeInOutCubic, lock: true, onComplete })`. While gliding, `isGliding = true`:
  - **Entrance reveals are suppressed.** Sections passed on the way show their settled state, so nothing pops at speed.
  - **Scroll-linked carriers** (below) and the kiosk's slight parallax scrub naturally, because they're tied to scroll position. That's what makes it read as a camera move.
  - The **active tab switches immediately to the destination**, so the underline slides once. The kiosk screen crossfades to the destination's state at the same moment.
  - On `onComplete`, `isGliding = false` and the **destination section builds in** (700–900 ms, stagger 60 ms).
  - Update the hash with `history.replaceState`. On load with a hash, skip the intro and jump to the section (no glide).
- **Active tab underline:** a single 2 px red `motion.span` with `layoutId="tab-underline"` that slides between tabs (250 ms, EASE). While scrolling, the active tab comes from which `data-tab` section crosses 40% of the viewport.
- **Scroll progress hairline:** 1 px, `#EEF1F5` at 60% opacity, fixed to the very top above the tab bar, `scaleX` from `useScroll().scrollYProgress` (transform-origin left).
- **Keyboard:** tabs are real `<a href="#id">` links. Focus rings use a 1 px near-white outline with 2 px offset. Never red.

### Section-to-section connecting moves (one continuous shot)

Each boundary has one element that **carries across**, so the eye never loses its place. All of these are scroll-linked (`useScroll({ target, offset })` + `useTransform`) unless noted. Each is one fixed-position "carrier" that maps between two measured rects by scroll progress, then hands off to the real element with a 1-frame swap. No shared-element routing, so it's buildable.

1. **Loader → Hero:** the red bracket mark becomes the kiosk's catch brackets (FLIP, see Intro).
2. **Hero → Replay 1 ("the replay emerges from the kiosk"):** as the hero scrolls out (`offset: ['start start', 'end start']`), **a copy of the kiosk screen card lifts off the screen** and travels and scales into the "With guard" panel. Its bracketed trick line lands on the same line inside the guarded panel's popup. Meanwhile **the kiosk itself recedes and stays**: it shrinks into its small background spot instead of leaving. The "Without guard" panel emerges beside it at `rotateY(8deg)`. Both panels flatten to `rotateY(0)` as they reach viewport center.
3. **Replay 1 → Replay 2 (in-section switcher, not a tab):** the browser chrome and URL bar **hold still**. Only the content crossfades (250 ms). Then the copycat letter flip plays: `brightcell.shop`, the `l` flips to `1` over 400 ms, and a **dashed** red bracket settles around just those characters.
4. **Replay → Benchmarks ("the counter becomes the headline number"):** the receipt prints (lines 120 ms apart), then the counters land: "Unguarded: −$X" (red) and "Guarded: −$0.00" (white). As Benchmarks enters, the **red counter fades out in place** (red never travels into our claims). The **white guarded counter is the carrier**: it rises into the Benchmarks H1 slot and its digits roll (tabular, 600 ms) from `$0.00` to `[X]%`, completing "Catches [X]% of checkout tricks." The kiosk screen switches to its miniature bar.
5. **Benchmarks headline → chart:** the hairline under the H1 extends full width and becomes the chart's 100% gridline. Gridlines draw left→right (stagger 60 ms). The SureShop dot (white) appears at its point, then the dashed "1/[N] the cost" connector draws from the Sonnet dot to ours (900 ms, `pathLength`).
6. **Benchmarks → Design process ("the dot becomes the loop"):** the white ring around the SureShop dot is the carrier. It scales up and stretches into the Design-process loop ellipse (`hairline-strong`, 1 px). The four loop nodes then light in order 01 → 04 (stagger 120 ms), and a single near-white tick travels once around the loop. It isn't continuous: nothing moves when idle. The kiosk screen shows its tiny loop.
7. **Design process → Future ("the miss feeds the next lesson"):** node 04, "Misses go back into training", drops a near-white dot that runs down a vertical hairline into the `01` index of the Future list. Each row's top hairline draws left→right (stagger 60 ms), then the row text enters.
8. **Future → Footer:** no carrier. The last hairline becomes the footer rule. The footer is static.

Tab glides pass through these same carriers (they're tied to scroll), so a click from Demo to Future is the whole camera move at 1.1 s speed, then the destination builds in.

### Reduced motion and fallbacks

- `prefers-reduced-motion: reduce` → no intro (settled hero, brackets already near-white, label showing), static background kiosk (no parallax, no recede animation, screen fixed on the Demo state), no tilt, sweep, roll or carrier travel. Panels render flat with damage fills in place. Tab clicks jump (`lenis.scrollTo(..., { immediate: true })`). Durations collapse to 0.01 ms.
- No WebGL or slow device (`navigator.hardwareConcurrency <= 4` or canvas creation fails) → poster image of the kiosk with the same DOM screen overlay in the hero, and a static small poster in the background spot. The catch still plays.
- Touch: Lenis off for touch (native momentum). Carriers still scrub from native scroll. Under 640 px the background kiosk is hidden.

## Signature interactions

### Bracket cursor (desktop only)

- **What:** on `(pointer: fine)` devices the cursor is **four tiny near-white corner brackets** (~14 × 14 px box, 1.5 px strokes, 5 px arms) centered on the pointer. It's the same visual language as a catch, but in near-white.
- **Snap:** hovering any interactive element (tabs, buttons, the Replay 1/2 toggles, links, anything with `[data-cursor="snap"]`, `a`, `button`, `[role="tab"]`) **snaps the brackets to that element's bounding box + 4 px** in **150 ms with `EASE`**. They release back to 14 px on leave (150 ms). The four corners move as one; no trailing, no elastic lag.
- **Color:** `#EEF1F5` only, at 90% opacity. **Never red.** Red is reserved for catches.
- **Native cursor kept for** text inputs, textareas and `contenteditable` (show the I-beam and hide the brackets while over them). There are none on the site today, but the rule stands.
- **Off when:** touch / `(pointer: coarse)` or no hover → custom cursor not mounted. `prefers-reduced-motion` → native cursor (custom cursor not mounted).
- **Must not lag (implementation):**
  - One `'use client'` component, `<BracketCursor/>`, mounted once in the layout, `position: fixed; pointer-events: none; z-index: 60` (above content, below nothing interactive).
  - `pointermove` writes the target into a ref. One `requestAnimationFrame` loop sets `transform: translate3d()` on the four corner nodes. The box grows and shrinks by moving the corners apart, never by resizing anything. **Transform-only, no React state per frame**, no Framer `animate` per move.
  - The snap target is found with `pointerover`/`pointerout` delegation + `closest(SNAP_SELECTOR)`. Its rect is read once on enter and on scroll (Lenis `scroll` event), not every frame.
  - The 150 ms snap is a per-frame interpolation in the rAF loop using the `EASE` curve (precomputed `bezier-easing`, or an inline cubic-bezier function). It isn't a CSS transition fighting the rAF writes.
  - `html { cursor: none }` only while the component is mounted and active; restore on unmount.

### One hidden trick per section (the site guards itself)

The site quietly proves the product: **each section after the replay hides one small, everyday checkout trick**, and SureShop catches it as you scroll by. They're drawn from our trick taxonomy (popup add-on, pre-checked extra, hidden/drip fee, checkout price change, subscription trap, fake urgency):

| Section | Trick (taxonomy) | Element (real-looking, small) | Brackets | Label |
|---|---|---|---|---|
| Benchmarks | **Pre-checked extra** | A pre-checked checkbox under the chart's axis captions: "☑ Add extended analysis +$4.99" | Solid (adds money) | `Blocked · pre-checked add-on` |
| Design process | **Fake urgency** | A store-style badge under "One call before your agent pays.": "Only 2 left!" | Dashed (a lie) | `Blocked · fake urgency` |
| Future | **Subscription trap** | A pre-checked line under the list: "☑ Subscribe & save 10% · renews at $12.99/mo" | Solid (adds money) | `Blocked · subscription trap` |
| Footer | **Hidden/drip fee** | A tiny fee line between the wordmark and the footer text: "Service fee +$1.49" | Solid (adds money) | `Blocked · drip fee` |

**Bracket style rule (clarified):** **solid = something that adds money to your order** (add-on, pre-checked extra, drip fee, subscription). **Dashed `[4,3]` = something false** (copycat store, listing injection, fake urgency, fake verification, a price that changes at checkout).

- **Trigger:** when the trick element is ~60% into the viewport (`useInView({ amount: 0.6, once: true })`) and `isGliding` is false. A glide that passes it leaves it uncaught. It plays when the visitor actually stops there.
- **The catch (calm, ~1.2 s):** red corner brackets lock onto the element in **one smooth move (400 ms, `EASE`, no overshoot, no glow surge)** → the mono 12 label fades in below it (250 ms, `text-2`) → the element dims to 50% and gets a strike-through (250 ms) → the brackets **settle to near-white** (500 ms). Same grammar as the hero catch, just smaller.
- **Once per session per section:** store caught ids in `sessionStorage` (`sureshopCaught`). Already-caught tricks render in the caught end state.
- **Reduced motion:** render the caught end state immediately (near-white brackets, label, dimmed + struck).
- **Never confused with real content:**
  - Small: element text 12–14 px, `text-2`, never larger than body copy, never inside a chart, table, replay panel or code block.
  - Placed in gutters or between blocks with ≥ 48 px clearance from real data. It never covers or sits inside a data block.
  - Copy is obviously store copy (prices, "Only 2 left!", "Subscribe & save"). It never contains numbers that could be read as our results.
  - Not interactive: the checkbox can't be toggled, and nothing is a link. The bracket cursor doesn't snap to them.
  - Uncaught state lasts only until it's 60% in view, so judges almost always see it caught.
- **Figma (caught end states, placed):** Benchmarks `29:2`, Design process `29:10`, Future `29:14`, footer (in 04 Future's footer) `29:22`. The site has one footer, so the drip fee appears once.

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
| `GLIDE` | 1.1 s | Tab glide (loader mark flight 0.9 s, camera pull-back 1.0 s) |
| `INTRO` | ~4 s total | Loader 0.7 s → mark 0.9 s → catch 1.4 s → pull-back 1.0 s |
| `CATCH` | ~1.4 s total, calm and steady | Dim to 60% (400 ms), one slow sweep (700 ms), brackets lock in one move (400 ms), readout fades in (250 ms), settle to white (500 ms). **The only beat allowed to exceed 1.1 s** |
| Kiosk parallax | ≤ 24 px / ≤ 4° over the whole page | Background kiosk only, scroll-mapped |
| Kiosk screen state | 250 ms crossfade | When the active section changes |
| Cursor snap | 150 ms, `EASE`, rAF-interpolated | Snap to and release from interactive elements |
| Hidden-trick catch | lock 400 ms → label 250 ms → dim + strike 250 ms → settle 500 ms | At 60% in view, once per session per section |
| Receipt print | 120 ms per line | Thermal-printer feel |
| Letter flip | 400 ms | Copycat `l`→`1` |
| Halo | steady ≤ 20% opacity, fade 500 ms | Catch only. No surge |

- **Panels tilt in depth:** the parent gets `perspective: 1600px`. The left panel starts at `rotateY(8deg)`, the right at `rotateY(-8deg)` (inner edges away), and both ease to `rotateY(0)` as they reach viewport center (scroll-linked). Shadows tighten as they flatten (`0 40px 80px rgba(0,0,0,.55), 0 8px 16px rgba(0,0,0,.45)`), with a blurred black floor plane (28 px blur) under each.
- **Animate only `transform` and `opacity`** (plus `filter` for the catch glow and `pathLength` for SVG draws). Never animate layout properties.
- **Nothing moves when idle.** No loops, pulses or ambient drift after the intro. The background kiosk moves only with scroll.
- **Calm, not tense:** no shake, flicker, strobe, overshoot, bounce, spring wobble, count-up flicker or glow surge anywhere. Springs, if used at all, are critically damped.
- `prefers-reduced-motion` collapses all durations (see above). Use `useReducedMotion()` in any component with custom timing.
- **3D is isolated in client components** (`'use client'`, dynamic import, `ssr:false`). Server components render static layout only.
- **Never mix GSAP and Framer Motion in the same component.** The default stack is Lenis + Framer, and GSAP should not be needed. If one isolated component truly needs it, it owns that component entirely.

## Banned list (never ship)

- Gradients of any kind: backgrounds, text, buttons, borders, shader "silk" waves
- Glass: frosted panels, `backdrop-filter: blur`, glassmorphism cards
- Parallax on data, text or panels. The **only** parallax allowed is the small background kiosk (≤ 24 px / ≤ 4°)
- Shake, flicker, strobing scan lines, glow surges, overshoot/bounce. One slow sweep at the catch is the limit
- The kiosk over data or text, or as a large hero after the intro; it recedes to the background and stays small
- Section changes that read as channel switching (cuts, wipes, shutters, page swaps)
- A floating or bobbing kiosk. It moves only with scroll or during the intro.
- Per-letter or per-word text reveals, text scramble/scatter, typewriter headings (receipt lines typing out is the one exception, line by line)
- Extra accent colors (no green "success", no blue links, no amber). Red is the only accent.
- Red on our own claims, catch rates, the SureShop chart dot, the guard or decoration
- "Example data" labels or placeholder numbers in production
- Sponsor branding, model-vendor logos, hackathon badges in the UI
- Shield, lock or robot icons representing the guard, and mascots
- Emoji, pill buttons, bubble radius, 3-column icon-in-circle feature grids
- Auto-playing carousels, confetti, particle storms, and any custom cursor other than the near-white bracket cursor (no trails, blobs or fluid cursors, and never a red cursor)
- Text smaller than 12 px, or reading text darker than `#9AA3AE`

## Component decisions

| Component / technique | Decision | Notes |
|---|---|---|
| Lenis smooth scroll | ✅ Allowed | The one scroll engine. `lerp 0.09`, native on touch |
| Framer Motion (`useScroll`, `useTransform`, `useInView`, `layoutId`, `MotionConfig`) | ✅ Allowed | The default motion library |
| React Three Fiber + drei (`<Html transform>`, `PerspectiveCamera`) | ✅ Allowed | Kiosk only: one fixed background canvas that persists across sections, hidden under 640 px. `MeshStandardMaterial #11141A`, roughness 0.8, 1 px `#323A45` edges, one `#EEF1F5` rim light upper-left |
| SVG `pathLength` draws (chart connector, gridlines, loop) | ✅ Allowed | |
| Custom tabular digit roll (counter → headline) | ✅ Allowed | Build it in-house (about 40 lines). No library |
| FLIP carrier elements (measured rects + scroll progress) | ✅ Allowed | The connecting moves |
| Subtle static noise texture | ⚠️ Conditional | Behind the kiosk only, ≤ 4% opacity, static (no animated grain), never over data |
| GSAP / ScrollTrigger | ⚠️ Conditional | Only if Framer can't do a specific beat, and only in its own component. Never with Lenis-Framer scroll-linked code in the same component |
| `@react-three/postprocessing` (bloom etc.) | ⚠️ Conditional | Skip unless the kiosk looks flat. Glow stays CSS `drop-shadow` on DOM brackets |
| View Transitions API | ❌ Skip | This is a single page; carriers handle continuity |
| Bracket cursor (in-house, rAF + transforms) | ✅ Allowed | Desktop `pointer: fine` only; native cursor on touch, text inputs and reduced motion |
| Hidden-trick catches (in-house, Framer `useInView`) | ✅ Allowed | One per section, small, non-interactive |
| React Bits fluid cursor / smooth cursor / splash cursor | ❌ Skip | Only the bracket cursor is allowed |
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
| 2026-10-17 | Kiosk persists after the intro as a small, dim, fixed background object (~20–25% vh, right gutter, behind content), with its screen mirroring the current section | Shardul: the kiosk is the anchor of "one space". Small and low contrast so it never competes with data. Hidden or static under 640 px and with reduced motion. |
| 2026-10-17 | Hero → Replay: the replay panels emerge from the kiosk screen (a copy lifts off) while the kiosk recedes and stays; **replaces "screen card becomes the panel and leaves"** | It keeps the anchor on stage, so the replay reads as coming out of the same machine. |
| 2026-10-17 | Feel: confident and calm. Intro shortened to ~4 s; dim softened to 60% (was 28%); no glow surge (faint ≤ 20% halo); brackets lock in one smooth move; one slow sweep, no strobe, shake or flicker | Shardul's feel answer. A calm product reads as trustworthy; tension reads as alarm. Supersedes the 28% dim and 45% glow in Figma M/T frames for motion. |
| 2026-10-17 | Navigation = a camera dolly/track through one continuous space around the background kiosk. The kiosk's slight parallax is the only parallax allowed, and never on data | Shardul: not channel switching. Carriers are kept; the kiosk's tiny shift sells the depth. |
| 2026-10-17 | Memorability = the use case. Use-case line added under the tagline on the landing (`26:2`) and on the table card (`26:3`); old hero sub-line `17:601` hidden; replay caption retold as the batteries story | Shardul: judges must remember what it's for and how useful it is. The one-glance test is that a passer-by can repeat "it stops the $9.99 add-on before your agent pays". |
| 2026-10-17 | Bracket cursor on desktop: four tiny near-white corner brackets that snap to interactive elements in 150 ms; never red; native cursor on touch, text inputs and reduced motion; rAF + transform-only | Shardul approved. It extends the bracket language to every hover, so the whole site feels like it's being checked, while red stays reserved for catches. |
| 2026-10-17 | One hidden trick per section (Benchmarks: pre-checked add-on; Design process: fake urgency; Future: subscription trap; footer: drip fee), caught at 60% in view, once per session | Shardul approved. The site guards itself, which shows the use case instead of claiming it. Small, non-interactive and away from data so it's never mistaken for content. Figma end states `29:2`, `29:10`, `29:14`, `29:22`. |
| 2026-10-17 | Bracket style clarified: solid = adds money (add-on, pre-checked, drip fee, subscription), dashed = false (copycat, injection, urgency, verification, price change) | Needed a rule that sorts all six taxonomy items unambiguously. |
| 2026-10-17 | Sonnet claim is data, per slice. Hero shows one slice (`hero_slice`, default familiar pages). Benchmarks shows all three slices and their error bars. "at 1/[N] the cost" only when both models have `cost_per_page_usd`. Synthetic results stay hidden | "baseline-level, at 1/[N] the cost" overclaims. Level-with vs within follows the slice's `claim` field and defaults to within. The cost ratio is not invented. |

## Open questions

- Demo format (laptop, projector or recorded video): on a projector, raise `text-2` usage to `text` for captions and bump Micro to 13 px.
- The `$9.99` in the use-case line must match the recorded replay at freeze.
- Final `[X]`, `[N]` and Sonnet gap/CI land after the frozen-test run, in a non-synthetic results file. The copy rule above decides "beats" vs "within".
- Site URL for the table-card QR (after Vercel deploy).
