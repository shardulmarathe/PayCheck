# Showcase site

Static SureShop site. The user-facing name is the `PRODUCT_NAME` constant in `src/lib/product.ts`. The npm package name stays `guard-gym`.

```bash
cd web
npm install
npm run dev
npm run build
```

Dev and preview bind to `0.0.0.0` and `PORT` (default 5173). `npm run build` typechecks, then writes `dist/`.

Data shapes and the `runs/` layout are in [DATA.md](./DATA.md).

Showcase site. It reads JSON run data from `runs/`. Shopper replays for the site are the non-synthetic files in `runs/shopper/` (`synthetic: false`, and `guard_backend: http` when the run is guarded). Mock runs live in `runs/shopper/synthetic/` and are not site data.

The headline demo is the exception committed for the site: `runs/shopper/hero-batteries_unguarded.json` and `runs/shopper/hero-batteries_guarded.json`. Read the add-on price from `hero_addon_usd` on those replays.

Every replay has `provenance`. Show it. `"scripted"` means the offline mock policy drove the browser, not a Browser Use agent and not an LLM. Both committed headline replays are `"scripted"`; label them that way and do not present them as a live model run. A real run is an object `{"kind":"real","model","timestamp","browser_use_version"}`. Show the model, the timestamp, and the Browser Use version.
