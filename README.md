# Checkout guard

A checkout guard for a shopping agent. Before the agent pays, it sends the page to a small model. The model returns block or pass, the trick type, the exact quoted evidence, and a short instruction for how to steer around the trick.

This repository is private.

| Path | What it is |
| --- | --- |
| `gym/` | Fake stores, trick specs, labels, the frozen test set, and the local shop server |
| `train/` | Training and eval (another agent) |
| `shopper/` | Browser Use shopper, with and without the guard. `python -m shopper.run --mock` runs offline |
| `web/` | Showcase site |
| `runs/` | JSON run data the showcase site reads |
| `data/` | Yada dark-pattern strings and the frozen test pages |

Python 3.11 or newer. Generation was checked with 3.12, Playwright 1.64.0, and Liberation Sans.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
# Debian/Ubuntu: sudo apt-get install -y fonts-liberation
```

## Commands

```bash
python -m gym.dataset --check          # frozen page-id split still matches the seed
make testset                           # rebuild the 300-page test set and require the same hash
make test
python -m gym.train --round 1 --n-train 1500 --n-dev 300
python -m gym.train --round 2 --n-train 1500 --n-dev 300
python -m gym.render_specs --specs-dir DIR --out data/attacker-round2 --source attacker-round2
python -m gym.serve --port 8765
python -m shopper.run --errand all --mode both --mock --guard-backend mock
```

Mock shopper runs are written to `runs/shopper/synthetic/` and are not site data. Real runs (a live model and, when guarded, an HTTP guard) go to `runs/shopper/`.

`make testset` does not rewrite the committed files. `python -m gym.testset --write` does, and should be a no-op diff when the font and browser match.

The shop server is at [Checkout guard gym](http://127.0.0.1:8765) once `python -m gym.serve --port 8765` is running. Give the agent the errand instruction and the start URL only. Trick type and the correct cart are on `/errands.json` for the harness. Card fields are discarded and not stored.

Sixty test pages are a template holdout: different stores and `reserved.html.j2`, which the train generator does not import. `copycat_domain` and `listing_injection` are tagged `heldout_attack`. The rest of the in-template pages are `in_dist`. Similarity against round 1 is in the test-set manifest.

## Frozen test set

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

`gym/testset/slice100.txt` is the 100-page stratified slice (50 clean, and every attack, including all three add-on variants).

Round-1 train and dev specs are `gym/rounds/r1/train.jsonl` and `gym/rounds/r1/dev.jsonl`. Shortcut-gate results for the test set and that round are in `gym/audit/shortcut_report.json`. The test token probe is 0.4236 and the test structure probe is 0.1362. Round-1 token AUCs are above the 0.65 gate (train 0.9582, dev 0.8208) and are listed there as known limitations.

Schemas, the label row, and the guard output contract are in `gym/schema/README.md`.
