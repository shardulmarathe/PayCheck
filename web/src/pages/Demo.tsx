import { motion } from "framer-motion";
import { ExampleMark } from "../components/Chrome";
import { KioskHero } from "../components/KioskHero";
import { ReplayScene } from "../components/Replay";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { EASE } from "../lib/ease";
import { formatUsd } from "../lib/format";
import { TAGLINE_LINES } from "../lib/product";
import type { Dataset, UpsellReplay } from "../lib/types";

function comparisonLine(replay: UpsellReplay): string {
  return `Same errand, same store: ${formatUsd(replay.without.paid)} without the guard, ${formatUsd(replay.with.paid)} with it.`;
}

export function Demo({ data }: { data: Dataset }) {
  const reduced = usePrefersReducedMotion();
  const featured = data.replays.find((replay) => replay.scene === "upsell") ?? data.replays[0];
  const rest = data.replays.filter((replay) => replay !== featured);

  return (
    <div className="wrap">
      <section className="section beat-hero" aria-labelledby="hero-title">
        <div className="hero-lockup">
          <div>
            <p className="label">{data.hero.eyebrow}</p>
            <motion.h1
              id="hero-title"
              className="display"
              initial={reduced ? false : { opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: reduced ? 0 : 0.9, ease: EASE }}
            >
              {TAGLINE_LINES[0]}
              <br />
              {TAGLINE_LINES[1]}
            </motion.h1>
          </div>
          <KioskHero />
        </div>
      </section>

      {featured ? (
        <ReplayScene
          replay={featured}
          example={data.example.replays}
          autoplay="mount"
          entrance
          tilt={featured.scene === "upsell"}
          textControl
        />
      ) : null}

      {featured?.scene === "upsell" ? (
        <section className="section beat-compare" aria-label="Comparison">
          <h2 className="comparison-line">{comparisonLine(featured)}</h2>
          <ExampleMark show={data.example.replays} />
        </section>
      ) : null}

      {rest.map((replay, index) => (
        <ReplayScene
          key={replay.id}
          replay={replay}
          label={`Replay ${index + 2}`}
          example={data.example.replays}
          autoplay="view"
        />
      ))}
    </div>
  );
}
