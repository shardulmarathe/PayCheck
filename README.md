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

## Showcase site (web/)

The static site lives in `web/`. The user-facing product name is SureShop (`PRODUCT_NAME` in `web/src/lib/product.ts`). The repository and the `web` package name stay guard-gym. This repository is private.

```bash
cd web && npm install && npm run dev
cd web && npm ci && npm run build
```

`npm run dev` serves the site on `0.0.0.0` and `$PORT` (or 5173). `npm run build` typechecks and writes static files to `web/dist`.

The Demo landing is three beats: the tagline with a lazy React Three Fiber checkout kiosk, a Replay 1 / Replay 2 switch in one slot, and one comparison line. The kiosk turns with scroll, pauses offscreen, and falls back to `kiosk-hero-crop.webp` for reduced motion, viewports under 768px, and no WebGL. Tab changes and the replay switch use a shutter cut. Latency readouts go through `formatLatency` and stay `[N] ms` until a real log exists. The Benchmarks headline and the comparison caption live in `web/src/lib/copy.ts`. The site is still a static Vite export.

The loader reads `runs/` at dev and build time and falls back, per section, to fixtures in `web/loader/fixtures.ts`. Blocks still on fixtures show an **example data** label. Drop real JSON in `runs/eval/`, `runs/training/`, `runs/replays/`, and `runs/tally.json` and the matching label goes away. Shapes are in `web/DATA.md`. `GUARD_GYM_FORCE_FIXTURES=1` keeps the fixtures even when `runs/` has files. There is no analytics and no live API.

Vercel: import this private repo, set Root Directory to `web`, framework preset Vite, build command `npm run build`, output directory `dist`. No environment variables are required.
