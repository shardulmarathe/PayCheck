# Showcase data

The site reads JSON from the repo-root `runs/` directory at dev and build time (`web/loader/loadDataset.ts`). A missing or invalid section stays on the fixture in `web/loader/fixtures.ts` and keeps its **example data** label. Set `GUARD_GYM_FORCE_FIXTURES=1` to ignore `runs/` entirely.

Catch rates are percents from 0 to 100. Do not store fractions. `isExample` on the loaded dataset is true only when eval, training, replays, and tally are all still fixtures. Per-section flags live on `example`.

| File | Replaces |
| --- | --- |
| `runs/eval/leaderboard.json` (or any other `runs/eval/*.json`) | summary table, cost scatter, the cost-gap label |
| `runs/training/*.json` (for example `round0.json`) | the design-process loop’s round and caught figure |
| `rounds` inside `runs/eval/*.json` | that same loop figure, only when `runs/training/` has no valid rounds |
| `runs/replays/*.json` | the Demo replays, the kiosk screen, and the comparison line |
| `runs/tally.json` | loaded, not drawn. v3 removed the tally strip |

Citations are copy, not run data. They stay in the fixture.

## Eval

`leaderboard.json` is either `{ "models": [ Model, ... ] }` or a bare array. Other files in `runs/eval/` are used only when the leaderboard is absent. Each file may be one model or `{ "models": [...] }`.

The object form may also carry the headline slot. `claim` is `"within"` unless it is exactly `"beats"`. `catch_pct`, `cost_ratio`, and `point_gap` are numbers. Leave them out and, once the eval is real, the loader fills them from the guard and Claude Sonnet rows: catch rate, Claude’s cost divided by the guard’s cost, and the guard’s catch rate minus Claude’s. `point_gap` is signed; positive means the guard is ahead.

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

While `catch_pct` is null, the catch line shows the literal `[X]`. The catch sentence lives in `web/src/lib/copy.ts`. The Sonnet sentence does **not** use `cost_ratio` or `point_gap`. It is built from the results file below. The cost-scatter gap line is labeled only when that file has a page-cost ratio, or when `point_gap` is a real number. It does not say `1/[N] the cost` as a placeholder.

## Results slices

`runs/eval/results.json` wins, then `runs/results.json`. Until one of those is present and not synthetic, the site keeps the checked-in mock at `web/loader/results.mock.json` **hidden**. `"synthetic": true` drops every score, claim, gap, and `cost_per_page_usd` in that file. Production then says "Within [N] points of the baseline model." and shows no slice error bars.

```json
{
  "synthetic": false,
  "hero_slice": "in_dist",
  "models": {
    "guard": { "label": "SureShop guard", "cost_per_page_usd": 0.00004 },
    "sonnet": { "label": "Baseline model", "cost_per_page_usd": 0.0062 }
  },
  "slices": {
    "in_dist": {
      "claim": "beats",
      "gap_points": 2.4,
      "scores": {
        "guard": { "score": 93.1, "ci_low": 89.4, "ci_high": 95.8 },
        "baseline": { "score": null, "ci_low": null, "ci_high": null }
      }
    },
    "heldout_attack": {
      "claim": "within",
      "gap_points": 5.5,
      "scores": {
        "guard": { "score": 84, "ci_low": 79.1, "ci_high": 88.2 },
        "baseline": { "score": null, "ci_low": null, "ci_high": null }
      }
    },
    "heldout_template": {
      "claim": "within",
      "gap_points": 3.1,
      "scores": {
        "guard": { "score": 88.4, "ci_low": 83.6, "ci_high": 92.1 },
        "baseline": { "score": null, "ci_low": null, "ci_high": null }
      }
    }
  }
}
```

- `hero_slice` is `in_dist` (familiar pages), `heldout_attack` (new attacks), or `heldout_template` (new templates). Anything else, including a missing field, is `in_dist`. The hero speaks only that slice, then a 12 px tag such as "on familiar pages".
- `claim` is `"within"` unless it is exactly `"beats"`. The hero says "Level with the baseline model" or "Within [N] points of the baseline model". `[N]` is `gap_points` when that number is present.
- Benchmarks joins the slices that exist: "Level with the baseline model on familiar pages, within 5.5 points on new attacks, within 3.1 points on new templates."
- Each score is a catch rate, 0–100. `ci_low` and `ci_high` together draw that model's error bar on the slice. One without the other draws the point only.
- `cost_per_page_usd` must be set on both `guard` (or `sureshop`) and `sonnet` (or `claude`) or the words "at 1/[N] the cost" are omitted. The ratio is Sonnet's page cost divided by ours. `cost_per_1k_checks_usd` does not fill this phrase.
- Model ids on a score row should match `models`. `guard` is drawn in near-white. Other dots stay `#9AA3AE`.

## Training

One object, or an array, per file:

```json
{ "round": 3, "catch_seen": 94, "catch_heldout": 84 }
```

`round` 0 is the untuned base. `catch_seen` is tricks like the training set. `catch_heldout` is trick types held out of training (`copycat_domain`, `listing_injection`). Both are percents.

v3 does not draw a round chart. The loop center uses the latest round. Files in `runs/training/` win. If that folder has no valid rounds, a `rounds` array on an eval JSON file is used instead:

```json
{ "rounds": [{ "round": 1, "catch_seen": 78, "catch_heldout": 63 }] }
```

## Replay

```json
{
  "id": "0142",
  "scene": "upsell",
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

## Tally

`runs/tally.json` is `{ "items": [ ... ] }` or a bare array.

```json
{
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
