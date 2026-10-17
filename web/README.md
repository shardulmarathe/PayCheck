# web/

Showcase site. It reads JSON run data from `runs/`. Shopper replays for the site are the non-synthetic files in `runs/shopper/` (`synthetic: false`, and `guard_backend: http` when the run is guarded). Mock runs live in `runs/shopper/synthetic/` and are not site data.

The headline demo is the exception committed for the site: `runs/shopper/hero-batteries_unguarded.json` and `runs/shopper/hero-batteries_guarded.json`. Read the add-on price from `hero_addon_usd` on those replays.
