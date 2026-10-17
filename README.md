# Checkout guard

A checkout guard for a shopping agent. Before the agent pays, it sends the page to a small model. The model returns block or pass, the trick type, the exact quoted evidence, and a short instruction for how to steer around the trick.

This repository is private.

| Path | What it is |
| --- | --- |
| `gym/` | Fake stores, trick specs, labels, the frozen test set, and the local shop server |
| `train/` | Training and eval (another agent) |
| `shopper/` | Browser Use shopper, with and without the guard |
| `web/` | Showcase site |
| `visa/` | Signed agent check (Visa Trusted Agent Protocol) and guarded payment |
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
python -m gym.train --round 1 --n 50
python -m gym.train --round 2 --n 50
python -m gym.render_specs --specs-dir DIR --out data/attacker-round2 --source attacker-round2
python -m gym.serve --port 8765
python -m visa.demo
```

`make testset` does not rewrite the committed files. `python -m gym.testset --write` does, and should be a no-op diff when the font and browser match.

The shop server is at [Checkout guard gym](http://127.0.0.1:8765) once `python -m gym.serve --port 8765` is running. Give the agent the errand instruction and the start URL only. Trick type and the correct cart are on `/errands.json` for the harness. Card fields are discarded and not stored.

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
8f07b8479900cca750ab8768728e1a913656dbcf1add7cc724b686a817396f45
```

`gym/testset/slice100.txt` is the 100-page stratified slice (50 clean, and every attack, including all three add-on variants).

Schemas, the label row, and the guard output contract are in `gym/schema/README.md`.

## Signed agent check (Visa Trusted Agent Protocol)

The agent signs checkout requests. The demo store checks the signature, then `pay()` calls the guard at `SURESHOP_CHECK_URL` and only then submits a payment. A block logs the trick and evidence and does not pay. A guard error does not pay. The demo processor is labeled `provenance: mock`.

```bash
python -m visa.demo
python -m visa.demo --check-url "$SURESHOP_CHECK_URL"
```
