import { motion } from "framer-motion";
import { KioskHero } from "../components/KioskHero";
import { ReplayScene } from "../components/Replay";
import { Shutter } from "../components/Chrome";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { useCut } from "../hooks/useCut";
import { useReplayChoice } from "../hooks/useRoute";
import { COPY } from "../lib/copy";
import { EASE } from "../lib/ease";
import { formatUsd } from "../lib/format";
import { TAGLINE_LINES } from "../lib/product";
import type { Dataset, UpsellReplay } from "../lib/types";

function money(n: number): string {
  return Number.isInteger(n) ? `$${n}` : formatUsd(n);
}

export function Demo({ data }: { data: Dataset }) {
  const reduced = usePrefersReducedMotion();
  const upsell = data.replays.find((replay): replay is UpsellReplay => replay.scene === "upsell");
  const [choice, select] = useReplayChoice();
  const target = data.replays.find((replay) => (choice === 2 ? replay.scene === "scam" : replay.scene === "upsell")) ?? data.replays[0];
  const { shown, phase } = useCut(target?.id ?? "replay");
  const visible = data.replays.find((replay) => replay.id === shown) ?? target;
  const addon = upsell?.without.lines.find((line) => line.damage);

  return (
    <div className="wrap">
      <section className="section beat-hero" aria-labelledby="hero-title">
        <div className="hero-lockup">
          <div className="hero-copy">
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
            <p className="hero-lead">A small, fast model reads every page and cart before your agent pays, and stops the trick.</p>
          </div>
          {upsell ? <KioskHero replay={upsell} example={data.example.replays} /> : null}
        </div>
      </section>

      {visible ? (
        <ReplayScene key={visible.id} replay={visible} example={data.example.replays} choice={choice} onChoice={select} />
      ) : null}
      <Shutter phase={phase} />

      {upsell && addon ? (
        <motion.section
          className="section beat-compare"
          aria-label="Comparison"
          initial={reduced ? false : { opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.6 }}
          transition={{ duration: reduced ? 0 : 0.9, ease: EASE }}
        >
          <div className="compare">
            <span className="compare-lost">{formatUsd(upsell.without.paid)}</span>
            <span className="compare-word">without</span>
            <span className="compare-dot">·</span>
            <span className="compare-kept">{formatUsd(upsell.with.paid)}</span>
            <span className="compare-word">with</span>
          </div>
          <p className="compare-caption">{COPY.comparisonCaption(money(upsell.budget), formatUsd(addon.amount), data.example.replays)}</p>
        </motion.section>
      ) : null}
    </div>
  );
}
