# Checkout guard

Hackathon monorepo for a checkout guard that blocks shopping-agent payment when a page hides a fee, a pre-checked add-on, a price change, a subscription trap, or a scam.

| Path | What it is |
| --- | --- |
| `gym/` | Fake stores, trick specs, labels, frozen test set, local shop server |
| `train/` | Training and eval (separate agent) |
| `shopper/` | Browser Use shopper |
| `web/` | Showcase site |
| `runs/` | JSON run data the showcase site reads |
| `data/` | Dataset, frozen test pages, generated train pages |

This repository is private.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
make test
make testset
python -m gym.serve --port 8765
```
