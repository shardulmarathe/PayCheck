# Showcase data

The site reads JSON from the repo-root `runs/` directory at dev and build time (`web/loader/loadDataset.ts`). Every benchmarks, replay, training-round, and tally file needs a top-level `"synthetic": true|false`. A missing flag counts as synthetic. Set `GUARD_GYM_FORCE_FIXTURES=1` to ignore `runs/` entirely.

`NEXT_PUBLIC_SHOW_EXAMPLES` is read when the dataset is built (Vite does not expose `NEXT_PUBLIC_*` to the browser). Unset, it is **false in production** and **true in `vite dev`**. `true` / `1` / `yes` shows fixtures and keeps the "example data" labels. `false` / `0` / `no` hides every section whose data is still synthetic: the block is not rendered, its numbers are left out of the client bundle, and the nav drops links to empty pages. The design-process and future pages stay, because they are copy. The training-loop ring reads `process.new_layout_pct` and `process.round_n`. Both stay null until a real new-layout result is filled in, and null renders as `[X]%` and `ROUND r[n]`. Do not copy `catch_seen` into that ring. If the replays are hidden, the landing page is the tagline and the kiosk.

Catch rates are percents from 0 to 100. Do not store fractions. `isExample` on the loaded dataset is true only when eval, training, replays, and tally are all still fixtures. Per-section flags live on `example`.

| File | Replaces |
| --- | --- |
| `runs/eval/leaderboard.json` (or any other `runs/eval/*.json`) | summary table, cost scatter, the cost-gap label |
| `runs/training/*.json` (for example `round0.json`) | loaded for the dataset; not drawn in the training loop |
| `rounds` inside `runs/eval/*.json` | the same training rounds, only when `runs/training/` has no valid rounds |
| `runs/replays/*.json` | the Demo replays, the kiosk screen, and the comparison line |
| `runs/tally.json` | loaded, not drawn. v3 removed the tally strip |

Citations are copy, not run data. They stay in the fixture. The problem-section source tags stay in `web/src/lib/problemSources.ts`.

## Round logs

`runs/r{N}/summary.json` and `runs/r{N}/replay.jsonl` use the pinned keys from `train/guardtrain/replay.py`. `npm run sync-data` copies them to `web/public/data/rounds/r{N}/`. The loader reads `runs/` and that public copy. `runs/` wins when the same round is in both.

The headline is the latest summary's `test.heldout_template.catch_rate` and `false_block_rate`. Those fields are fractions from 0 to 1; the site shows them as percents. A value above 1 is already a percent. `null` hides that slot. There is no `[X]` and no fixture number in its place. The same catch rate fills the design-process ring. The replay section steps through `replay.jsonl` (fed-back lines first, 120 ms apart, then the next round). A round with no lines is not drawn.

`summary.json` has no `synthetic` flag. A file that parses is real data, including in production.

## Browser Use

Per-run JSON lives in `runs/shopper/**/*.json` (not `tally.json` or `ledger.json`). `provenance` is `"scripted"` or `{ "kind": "real", "model", "timestamp", "browser_use_version" }`. Scripted runs are labeled "Scripted" and are omitted when examples are hidden. Real runs stay.

The section shows three slots, and hides a slot that cannot be computed:

- Paid-for-trick rate, unguarded and guarded. A run paid for the trick when `outcome` is `fell`, money was lost, a scam was recorded, or `unwanted_subscription` is true. The denominator is runs whose `attack_type` is not `none`.
- False-block rate: guarded runs with no attack type where a step has `blocked: true`, divided by those clean guarded runs.
- Dollars overpaid: the sum of `overcharge_usd` on each side. Unguarded money uses the red fill. Guarded money stays near-white.

MP4 files are served from `web/public/recordings/`. A run embeds one when `video` or `{errand_id}_{mode}.mp4` is there. `npm run sync-data` copies referenced `.mp4` files and anything under `runs/recordings/`. `--examples` also copies scripted and `"synthetic": true` shopper JSON. Without that flag, those files stay out of `web/public/data`.

## Visa

`runs/visa/*.json` is a trace. The section title is "Signed agent check (Visa Trusted Agent Protocol)". Stages render in order when present: signed agent request, store signature check, guard check, then pay or block. A missing stage is left out. `"synthetic": true` is omitted when examples are hidden. `npm run sync-data` copies the traces to `web/public/data/visa/`.

## Eval

`leaderboard.json` is `{ "synthetic": false, "models": [ Model, ... ] }`. A bare array, or a file without `"synthetic": false`, is hidden. Other files in `runs/eval/` are used only when the leaderboard is absent, and each of those also needs `"synthetic": false`.

The object form may also carry the headline slot. `claim` is `"within"` unless it is exactly `"beats"`. `catch_pct`, `cost_ratio`, and `point_gap` are numbers. Leave them out and, once the eval is real, the loader fills them from the guard and baseline-model rows: catch rate, Claude’s cost divided by the guard’s cost, and the guard’s catch rate minus Claude’s. `point_gap` is signed; positive means the guard is ahead.

```json
{
  "id": "guard",
  "model": "Guard · Qwen3-4B fine-tuned",
  "short": "Guard",
  "emphasis": true,
  "pages": 300,
  "catch_rate": 91,
  "catch_rate_300": 91,
  "catch_rate_100": null,
  "false_block_rate": 3,
  "evidence_match": 88,
  "latency_ms_median": 212,
  "cost_per_1k_checks_usd": 0.04,
  "ci_low": 87.8,
  "ci_high": 94.2,
  "catch_rate_by_attack": { "popup_add_on": 96 },
  "by_attack": {
    "popup_add_on": {
      "catch_rate": 96,
      "false_block_rate": null,
      "evidence_match": null,
      "latency_ms": 212,
      "cost_per_1k_checks_usd": 0.04
    }
  }
}
```

Required: `id`, `model`, `catch_rate`, `latency_ms_median`, `cost_per_1k_checks_usd`.

- `emphasis` (or `role: "guard"`) marks the fine-tuned guard. Its scatter point stays white with the glow ring.
- `ci_low` and `ci_high` are the 95% confidence interval in catch-rate percent. Both are required to draw that model’s error bar. The bar length is the interval, not a fixed pixel size. A missing pair draws no bar.
- `catch_rate_300` / `catch_rate_100` may be `null`. A model with only `catch_rate_100` is a hollow point. The vertical axis is 40–100; a catch rate under 40 sits on the 40 line.
- `catch_rate_by_attack` is keyed by attack row id: `popup_add_on`, `prechecked_extra`, `subscription_trap`, `hidden_fees`, `price_change`, `copycat_domain`, `fake_card_verification`, `listing_injection`. Popup add-on and pre-checked extra are both `preselected_addon` variants; they are separate rows.
- `by_attack` is optional. Without it, false-block and evidence-match cells are an em dash. Latency and cost repeat the model-level figure, because those are per check.
- `none` is the clean-page trick id used for the model-level false-block rate. It is not an attack row.

Latency cells use `formatLatency` in `web/src/lib/format.ts`. While a section is still example data, or the log has no latency, the site shows the literal `[N] ms`. A real value under 1000 ms renders as `212 ms`; 1000 ms or more renders as `1.4 s`.

While `catch_pct` is null, the catch line shows the literal `[X]`. The catch sentence lives in `web/src/lib/copy.ts`. The baseline sentence does **not** use `cost_ratio` or `point_gap`. It is built from the results file below. The cost-scatter gap line is labeled only when that file has a page-cost ratio, or when `point_gap` is a real number. It does not say `1/[N] the cost` as a placeholder.

## Results slices

`runs/eval/results.json` wins, then `runs/results.json`. Both need `"synthetic": false` or the scores stay out. Until one of those is present and not synthetic, the checked-in mock at `web/loader/results.mock.json` is schema only. With examples hidden, the Benchmarks page and its nav link are omitted entirely (no "Within [N]" placeholder, no slice bars). With examples on, the page shows fixture scores and an example-data label, and the baseline line stays "Within [N] points of the baseline model." because the mock slices are not rendered.

```json
{
  "synthetic": false,
  "hero_slice": "in_dist",
  "models": {
    "guard": { "label": "Guard" },
    "baseline": { "label": "Baseline model" }
  },
  "slices": {
    "in_dist": {
      "claim": "within",
      "gap_points": 0,
      "scores": {
        "guard": { "score": 0, "ci_low": 0, "ci_high": 0 },
        "baseline": { "score": null, "ci_low": null, "ci_high": null }
      }
    }
  }
}
```
Shape only. The scores above are zero placeholders, not results. Real results are in the repository README.

- `hero_slice` is `in_dist` (familiar pages), `heldout_attack` (new attacks), or `heldout_template` (new templates). Anything else, including a missing field, is `in_dist`. The hero speaks only that slice, then a 12 px tag such as "on familiar pages".
- `claim` is `"within"` or `"beats"`. The hero never says "beats": it says "Level with the baseline model" or "Within [N] points of the baseline model". `[N]` is `gap_points` when that number is present.
- Benchmarks joins the slices that exist, one phrase per slice, with no cost phrase.
- Each score is a catch rate, 0–100. `ci_low` and `ci_high` together draw that model's error bar on the slice. One without the other draws the point only.
- `cost_per_page_usd` is read but no cost ratio is spoken on the site.
- Model ids on a score row should match `models`. `guard` is drawn in near-white. Other dots stay `#9AA3AE`.

## Training

One object, or an array, per file:

```json
{ "synthetic": false, "round": 3, "catch_seen": 94, "catch_heldout": 84 }
```

A file may instead be `{ "synthetic": false, "rounds": [ ... ] }`. An array with no `synthetic` flag is hidden.

`round` 0 is the untuned base. `catch_seen` is tricks like the training set. `catch_heldout` is trick types held out of training (`copycat_domain`, `listing_injection`). Both are percents.

v3 does not draw a round chart. The loop center uses the latest round. Files in `runs/training/` win. If that folder has no valid rounds, a `rounds` array on an eval JSON file is used instead:

```json
{ "synthetic": false, "rounds": [{ "round": 1, "catch_seen": 78, "catch_heldout": 63 }] }
```

## Replay

```json
{
  "synthetic": false,
  "id": "0142",
  "scene": "upsell",
  "overcharge_usd": 9.99,
  "exposed": false,
  "subscription": false,
  "subscription_monthly_usd": null,
  "title": "AA batteries, 12-pack, under $15",
  "budget": 15,
  "duration_ms": 38000,
  "kicker": "Recorded replay · errand 0142",
  "meta_right": "Same store · same shopper · same errand",
  "shopper": "Shopper · Haiku via Browser Use",
  "timeline_caption": "Both replays share one timeline. Recorded, not live.",
  "steps": [
    { "t_ms": 0, "id": "search", "label": "Search", "tick": true, "kind": "search" },
    { "t_ms": 21000, "id": "catch", "label": "Caught", "tick": true, "catch": true, "kind": "catch" }
  ],
  "verdict": {
    "action": "block",
    "latency_ms": null,
    "category": "upsell",
    "trick": "popup add-on",
    "evidence": "By continuing, Battery Care+ ($9.99) is added to your order.",
    "steer": "Decline the add-on, then check out.",
    "expected_total": 14.48,
    "readout": "BLOCKED · UPSELL, SNEAKED INTO BASKET"
  },
  "scene_view": { "kind": "cart" },
  "without": {
    "kicker": "Without guard",
    "story_label": "Shopper",
    "story_body": "Clicked Continue.",
    "story_title": "Paid without noticing.",
    "lines": [
      { "label": "AA batteries, 12-pack", "amount": 13.49 },
      { "label": "Battery Care+", "amount": 9.99, "damage": true }
    ],
    "paid_label": "Paid",
    "paid": 24.47,
    "paid_note": "Over budget by $9.47",
    "outcome": "lost"
  },
  "with": { "outcome": "ok", "lines": [], "paid": 14.48 }
}
```

`scene` is `upsell` or `scam`.

- Upsell requires `scene_view.kind: "cart"` plus `without` and `with`. Receipt `lines` use `amount`, and optionally `damage` or `muted`. `paid` is the total. `outcome` is `lost` or `ok`.
- Scam requires `scene_view.kind: "scam"` plus `columns` (`flagged_label`, `trick_label`, `steer_label`). The cart scene and the scam scene fields are the full objects in `web/src/lib/types.ts`.
- Step `kind` is `search`, `product`, `popup`, `click`, `catch`, `paid`, or `other`. `tick` draws the shared timeline. `catch` is the red playhead dot.
- The settled readout uses `verdict.latency_ms` through `formatLatency`. `null` (and every fixture replay) shows `[N] ms`. Do not bake a design millisecond into the fixture.
- `overcharge_usd` is dollars paid above the expected total (shopper schema: `overcharge_usd`, same number as `dollars_lost`). The unguarded lane counts `lost $X.XX` in a solid red fill up to that amount. The count finishes by 20 seconds of autoplay. `0` draws no counter.
- `exposed` is true when card or bank details were submitted on a phishing page. It does not add a third headline.
- `subscription` is true for an unwanted subscription (`unwanted_subscription` or `final_cart.subscription` in `shopper/schema/replay.json`). `subscription_monthly_usd` is optional because that schema has no monthly price. When both are set, the unguarded lane adds `Signed you up for $X.XX/month`.
- The default fixture upsell uses `overcharge_usd: 9.99`, `exposed: false`, `subscription: false`, and reaches the full loss by 18 seconds (click at 14s, paid at 18s).

## Tally

`runs/tally.json` needs `"synthetic": false`. It is `{ "synthetic": false, "items": [ ... ] }`. A bare array is hidden.

The tally strip is not drawn. The loader still drops synthetic items so they are not shipped in the client bundle.

```json
{
  "synthetic": false,
  "id": "dollars",
  "label": "Extra dollars spent",
  "with_guard": 9,
  "without_guard": 412,
  "format": "dollars",
  "note": "with guard",
  "from_tone": "loss"
}
```

`format` is `count` or `dollars`. `from_tone` is `loss` (the unguarded figure is red, and the words still say what happened) or `muted`.
