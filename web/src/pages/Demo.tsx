import { motion } from "framer-motion";
import { useRef } from "react";
import { ReplayScene } from "../components/Replay";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { useReplayChoice } from "../hooks/useRoute";
import { useIntroPhase } from "../components/motion/Intro";
import { COPY } from "../lib/copy";
import { heroClaim } from "../lib/results";
import { EASE } from "../lib/ease";
import { formatUsd, trimNum } from "../lib/format";
import { STAGGER } from "../lib/motion";
import { TAGLINE_LINES } from "../lib/product";
import type { Dataset, UpsellReplay } from "../lib/types";

function money(n: number): string {
  return Number.isInteger(n) ? `$${n}` : formatUsd(n);
}

export function Demo({ data }: { data: Dataset }) {
  const reduced = usePrefersReducedMotion();
  const phase = useIntroPhase();
  const settled = useRef(phase === "done");
  const showCopy = phase === "done" || reduced;
  const story = data.shown.replays;
  const claims = data.shown.benchmarks;
  const upsell = story ? data.replays.find((replay): replay is UpsellReplay => replay.scene === "upsell") : undefined;
  const [choice, select] = useReplayChoice();
  const visible = story
    ? (data.replays.find((replay) => (choice === 2 ? replay.scene === "scam" : replay.scene === "upsell")) ?? data.replays[0])
    : undefined;
  const addon = upsell?.without.lines.find((line) => line.damage);
  const catchPct = data.benchmarks.catch_pct;
  const catchLabel = catchPct == null || !Number.isFinite(catchPct) ? "[X]" : trimNum(Math.abs(catchPct));
  const sonnet = heroClaim(data.results);
  const enter = (index: number) =>
    reduced || settled.current
      ? { duration: 0 }
      : { duration: 0.7, delay: index * STAGGER, ease: EASE };

  return (
    <div className="wrap">
      <section className="section beat-hero" aria-labelledby="hero-title">
        <div className="hero-lockup">
          <div className="hero-copy">
            {story ? (
              <motion.p className="label" initial={false} animate={{ opacity: showCopy ? 1 : 0, y: showCopy ? 0 : 12 }} transition={enter(0)}>
                {data.hero.eyebrow}
              </motion.p>
            ) : null}
            <motion.h1
              id="hero-title"
              className="display"
              initial={false}
              animate={{ opacity: showCopy ? 1 : 0, y: showCopy ? 0 : 12 }}
              transition={enter(1)}
            >
              {TAGLINE_LINES[0]}
              <br />
              {TAGLINE_LINES[1]}
            </motion.h1>
            {story && addon ? (
              <motion.p className="use-case" initial={false} animate={{ opacity: showCopy ? 1 : 0, y: showCopy ? 0 : 12 }} transition={enter(2)}>
                {COPY.useCase(formatUsd(addon.amount))}
              </motion.p>
            ) : null}
            {claims ? (
              <>
                <motion.p className="hero-claim" initial={false} animate={{ opacity: showCopy ? 1 : 0, y: showCopy ? 0 : 12 }} transition={enter(3)}>
                  {COPY.catchLine(catchLabel)}
                </motion.p>
                <motion.p className="hero-sonnet" initial={false} animate={{ opacity: showCopy ? 1 : 0, y: showCopy ? 0 : 12 }} transition={enter(4)}>
                  {sonnet.sentence}
                </motion.p>
                <motion.p className="slice-tag" initial={false} animate={{ opacity: showCopy ? 1 : 0, y: showCopy ? 0 : 12 }} transition={enter(5)}>
                  {sonnet.tag}
                </motion.p>
              </>
            ) : null}
          </div>
          <div id="kiosk-slot" className="kiosk-slot" />
        </div>
      </section>

      {visible ? (
        <ReplayScene replay={visible} example={data.example.replays} choice={choice} onChoice={select} />
      ) : null}

      {story && upsell && addon ? (
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
