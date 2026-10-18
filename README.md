# PayCheck

Live demo: https://paycheck-guard.vercel.app · About level with Claude Haiku 5.5 on F1 (0.776 calibrated vs 0.766; difference not significant), with 0/150 honest checkouts blocked vs 16/150.

PayCheck is a checkout guard for AI shopping agents. Before the agent pays, it sends the page to a small model. The model returns block or pass, the trick type, the exact quoted evidence, and a short instruction for how to steer around the trick.

The guard is Qwen3-4B-Instruct-2507 with a LoRA adapter trained on Veri. The demo shopper is a Browser Use agent, and payment goes through a signed agent check (our implementation of Visa's Trusted Agent Protocol) with mock payments only.

## Results

All numbers below come from two checked files: `REPORT.md` (the calibrated-threshold run on the locked test) and `training-cycle-facts.md` (the training and Browser Use recount). Both are listed under Data sources.

**Locked test set** (n = 300: 150 trick pages, 150 honest checkouts). Graded once per declared model.

| model | F1 | tricks caught | honest checkouts wrongly blocked |
| --- | ---: | ---: | ---: |
| PayCheck guard (r4), threshold calibrated on dev before the test | 0.776 | 95 / 150 | 0 / 150 |
| PayCheck guard (r4), no threshold | 0.740 [0.673, 0.799] | 88 / 150 | 0 / 150 |
| Claude Haiku 5.5 | 0.766 | 103 / 150 | 16 / 150 |

The calibrated guard is level with Claude Haiku 5.5 on F1: the paired bootstrap difference is +0.010, 95% CI −0.035 to +0.056, which includes 0. Where it differs is false blocks: 0 of 150 honest checkouts against Haiku 5.5's 16 of 150. It even catches some trick types it never saw in training.

**Browser Use shoppers.** 1,140 real AI-shopper runs across four batches. In the three batches that used the shipped r4 guard, shoppers on trick pages paid for the trick or handed over card details 133 of 238 times without the guard and 18 of 234 times with it. With the guard, 3 of 88 honest checkouts were wrongly stopped.

**Training on Veri.** Six rounds, growing from 1,500 to 7,176 training rows. The shipped guard (r4, Veri job `0a9a4b96274b`) is a Qwen3-4B-Instruct-2507 LoRA, r16, alpha 32, learning rate 2e-4, 1 epoch. The live guard serves an 8-bit (q8_0) GGUF copy.

### Data sources

- `REPORT.md` (internal eval report, not in this repo): locked-test scores for r4 with and without the calibrated threshold, the Haiku 5.5 baseline, and the paired bootstrap.
- `training-cycle-facts.md` (internal fact sheet, not in this repo): rows per round, Veri settings, and the Browser Use recount (run counts and guarded vs unguarded outcomes).
- Practice and test pages are built from fixed templates plus [yamanalab/ec-darkpattern](https://github.com/yamanalab/ec-darkpattern) (Apache-2.0).

The locked test pages and labels are not in this repository (see below), so these scores cannot be recomputed from the repo alone.

## Reproduce in 2 minutes

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
make test
```

`make test` should pass with some tests skipped: those tests read the locked test set, which is held back from this repository on purpose. `make testset` and `python -m gym.testset --write` print a skip notice for the same reason. To score a model, supply the locked test set (`data/testset/`, `gym/testset/`, `gym/splits/test_page_ids.txt`) separately.

The training and eval package is in `train/`. Its extras are `.[merge]` (torch, transformers, peft, to merge adapters) and `.[api]` (Anthropic and OpenAI clients for baselines):

```bash
cd train
pip install -e ".[dev]"            # add ".[merge]" or ".[api]" as needed
python -m pytest -q tests
```

## Repository layout

| Path | What it is |
| --- | --- |
| `gym/` | Fake stores, trick specs, labels, test-set tooling, and the local shop server |
| `train/` | Training and eval on Veri, local GGUF conversion, and offline scoring |
| `shopper/` | Browser Use shopper, with and without the guard. `python -m shopper.run --mock` runs offline |
| `web/` | PayCheck site (live at paycheck-guard.vercel.app) |
| `visa/` | Signed agent check (our implementation of Visa's Trusted Agent Protocol) and guarded mock payment |
| `runs/` | JSON run data the site loader can read |
| `data/` | Yada dark-pattern strings (the frozen test pages are held back) |

Python 3.11 or newer. Generation was checked with 3.12, Playwright 1.64.0, and Liberation Sans.

On Debian/Ubuntu, install the font with `sudo apt-get install -y fonts-liberation`.

## Commands

```bash
python -m gym.dataset --check          # frozen page-id split still matches the seed (needs the held-back split file)
make testset                           # rebuild the held-back test set and require the same hash (skips without it)
make test
python -m gym.train --round 1 --n-train 1500 --n-dev 300
python -m gym.train --round 2 --n-train 1500 --n-dev 300
python -m gym.render_specs --specs-dir DIR --out data/attacker-round2 --source attacker-round2
python -m gym.serve --port 8765
python -m shopper.run --errand all --mode both --mock --guard-backend mock
python -m visa.demo
```

Mock shopper runs are written to `runs/shopper/synthetic/` and are not site data. Real runs (a live model and, when guarded, an HTTP guard) go to `runs/shopper/`.

`make testset` does not rewrite the committed files. `python -m gym.testset --write` does, and should be a no-op diff when the font and browser match.

The shop server is at [PayCheck gym](http://127.0.0.1:8765) once `python -m gym.serve --port 8765` is running. Give the agent the errand instruction and the start URL only. Trick type and the correct cart are on `/errands.json` for the harness. Card fields are discarded and not stored.

Sixty test pages are a template holdout: different stores and `reserved.html.j2`, which the train generator does not import. The in-template pages are `in_dist`. Similarity against round 1 is in the test-set manifest.

## Frozen test set

The test pages, labels, manifest, and page-id split are held back from this public repository. The description below is for reference.

300 pages, half clean. Built from fixed templates plus the test pile of [yamanalab/ec-darkpattern](https://github.com/yamanalab/ec-darkpattern) (Apache-2.0). No model writes these pages. `copycat_domain` and `listing_injection` are only in this set. Training rounds do include `fake_card_verification`. Clean pages include honest look-alikes (an unticked checkbox, a popup whose default is "No thanks", a disclosed shipping or tax line, a real sale price, or a radio with the plain option selected) so page structure alone is not the label. See `gym/README.md`.

A fee is a checkout summary line. A price change is a higher price next to the struck shelf price. A checked add-on is labeled with the add-on it selects. A subscription quote is the pre-selected option on that page.

| attack_type | family | pages |
| --- | --- | ---: |
| `hidden_fees` | upsell | 24 |
| `preselected_addon` | upsell | 30 |
| `price_change` | upsell | 24 |
| `subscription_trap` | upsell | 24 |
| `copycat_domain` | scam | 16 |
| `fake_card_verification` | scam | 16 |
| `listing_injection` | scam | 16 |
| `none` | clean | 150 |
| **total** | | **300** |

`preselected_addon` is 10 pre-checked add-ons, 10 popups that sneak an item into the cart, and 10 one-click offers.

Content hash (SHA-256, see `gym/schema/README.md`):

```
6370babfc63770777827e113eb5e04cf48cc304e18cb16333e23351d85f22fcc
```

Round-1 train and dev specs are `gym/rounds/r1/train.jsonl` and `gym/rounds/r1/dev.jsonl`. Shortcut-gate results for the test set and that round are in `gym/audit/shortcut_report.json`. The test token probe is 0.4236 and the test structure probe is 0.1362. Round-1 token AUCs are above the 0.65 gate (train 0.9582, dev 0.8208) and are listed there as known limitations.

Schemas, the label row, and the guard output contract are in `gym/schema/README.md`.

## Signed agent check (our implementation of Visa's Trusted Agent Protocol)

The agent signs checkout requests. The demo store checks the signature, then `pay()` calls the guard at `SURESHOP_CHECK_URL` with gym reader text (including the advertised item and price) and only then submits a payment. A block logs the trick and evidence and does not pay. A guard error, including a timeout (`SURESHOP_GUARD_TIMEOUT_S`, default 60s), does not pay and is recorded as `guard error`. The demo processor is labeled `provenance: mock`.

```bash
python -m visa.demo
python -m visa.demo --check-url "$SURESHOP_CHECK_URL"
```

## Site (web/)

`web/` is the source of the live PayCheck site, https://paycheck-guard.vercel.app. It is a Vite + React static site plus one server function, `web/api/check.ts`, which backs the "Try it" panel. The user-facing product name is `PRODUCT_NAME` in `web/src/lib/product.ts`; the npm package is `paycheck-site`.

```bash
cd web && npm install && npm run dev
cd web && npm ci && npm run build
```

`npm run dev` serves the site on `0.0.0.0` and `$PORT` (or 5173). `npm run build` typechecks and writes static files to `web/dist`. Site copy lives in `web/src/lib/copy.ts`; data shapes are in `web/DATA.md`.

`web/api/check.ts` only forwards a fixed allowlist of recorded demo pages to the guard; visitor text is never forwarded. It reads two server-only environment variables, `PAYCHECK_GUARD_URL` and `PAYCHECK_GUARD_TOKEN`, set in the Vercel project settings (never `VITE_`-prefixed). Without them the panel plays the recorded results.

Vercel: import this repo, set Root Directory to `web`, framework preset Vite, build command `npm run build`, output directory `dist`.
