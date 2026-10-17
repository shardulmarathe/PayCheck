# Showcase data

The site reads JSON from the repo-root `runs/` directory at dev and build time (`web/loader/loadDataset.ts`). A missing or invalid section stays on the fixture in `web/loader/fixtures.ts` and keeps its **example data** label. Set `GUARD_GYM_FORCE_FIXTURES=1` to ignore `runs/` entirely.

Catch rates are percents from 0 to 100. Do not store fractions. `isExample` on the loaded dataset is true only when eval, training, replays, and tally are all still fixtures. Per-section flags live on `example`.

| File | Replaces |
| --- | --- |
| `runs/eval/leaderboard.json` (or any other `runs/eval/*.json`) | model table, latency, cost scatter, hero median, cost headline |
| `runs/training/*.json` (for example `round0.json`) | both catch-rate-by-round charts and the loop’s round / caught figure |
| `rounds` inside `runs/eval/*.json` | the same round charts, only when `runs/training/` has no valid rounds |
| `runs/replays/*.json` | both recorded scenes and the sample `/check` response |
| `runs/tally.json` | the per-100-errands tally |

Citations are copy, not run data. They stay in the fixture.

## Eval

`leaderboard.json` is either `{ "models": [ Model, ... ] }` or a bare array. Other files in `runs/eval/` are used only when the leaderboard is absent. Each file may be one model or `{ "models": [...] }`.

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
  "latency_ms_median": 41,
  "cost_per_1k_checks_usd": 0.04,
  "catch_rate_by_attack": { "popup_add_on": 96 },
  "by_attack": {
    "popup_add_on": {
      "catch_rate": 96,
      "false_block_rate": null,
      "evidence_match": null,
      "latency_ms": 41,
      "cost_per_1k_checks_usd": 0.04
    }
  }
}
```

Required: `id`, `model`, `catch_rate`, `latency_ms_median`, `cost_per_1k_checks_usd`.

- `emphasis` (or `role: "guard"`) marks the fine-tuned guard. Its latency bar is the text color.
- `catch_rate_300` / `catch_rate_100` may be `null`. On the 300-page scatter, a model with only `catch_rate_100` is drawn hollow. The 100-page toggle omits models whose `catch_rate_100` is null.
- `catch_rate_by_attack` is keyed by attack row id: `popup_add_on`, `prechecked_extra`, `subscription_trap`, `hidden_fees`, `price_change`, `copycat_domain`, `fake_card_verification`, `listing_injection`. Popup add-on and pre-checked extra are both `preselected_addon` variants; they are separate rows.
- `by_attack` is optional. Without it, false-block and evidence-match cells are an em dash. Latency and cost repeat the model-level figure, because those are per check.
- `none` is the clean-page trick id used for the model-level false-block rate. It is not an attack row.

When eval is real, the cost headline replaces the literal `[N]` / `1/[40]` placeholder from the guard and Gemini costs, and the hero median uses the guard’s `latency_ms_median`.

## Training

One object, or an array, per file:

```json
{ "round": 3, "catch_seen": 94, "catch_heldout": 84 }
```

`round` 0 is the untuned base. `catch_seen` is tricks like the training set. `catch_heldout` is trick types held out of training (`copycat_domain`, `listing_injection`). Both are percents.

The large Benchmarks chart draws both series. The small line under the cost chart draws `catch_seen` only, and the last point is the only red mark. Files in `runs/training/` win. If that folder has no valid rounds, a `rounds` array on an eval JSON file is used instead:

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
    "latency_ms": 41,
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
- The settled readout uses `verdict.latency_ms`, not a separate clock.

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
