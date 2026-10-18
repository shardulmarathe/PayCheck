import { useInView } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { SITE } from "../lib/copy";
import type { ModelEval } from "../lib/types";
import { CountUp } from "./motion/CountUp";
import { Pin } from "./motion/Pin";
import { TrainingLoop } from "./TrainingLoop";
import { Sign, Tag } from "./Sign";

/**
 * The wins, shown big. Benchmark numbers appear only where PayCheck wins.
 * Honest pages wrongly blocked on the 300-page benchmark: PayCheck 0 of 150, Claude Haiku 16 of 150 (11%).
 * Each square is one honest page; which squares light is decorative, the counts are exact.
 */
const HONEST = 150;
const HAIKU_FALSE = 16;
const HAIKU_PCT = 11;
// Deterministic spread of the 16 red squares across the 150.
const RED = new Set(Array.from({ length: HAIKU_FALSE }, (_, i) => Math.floor(((i + 0.5) * HONEST) / HAIKU_FALSE + ((i * 7) % 5) - 2)));

function PageGrid({ red }: { red: boolean }) {
  return (
    <span className="win-grid" aria-hidden="true">
      {Array.from({ length: HONEST }, (_, i) => (
        <i key={i} className={red && RED.has(i) ? "bad" : undefined} style={{ ["--i" as string]: i }} />
      ))}
    </span>
  );
}

export function WinsHero() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  return (
    <figure
      ref={ref}
      className={inView ? "win is-in" : "win"}
      aria-label={`Honest pages wrongly blocked on our 300-page benchmark: PayCheck 0 of ${HONEST}, Claude Haiku 5.5 ${HAIKU_FALSE} of ${HONEST} (${HAIKU_PCT}%).`}
    >
      <p className="cp-doc-head win-head" aria-hidden="true">
        <span>Inspection report</span>
        <span>PayCheck · Claude Haiku 5.5</span>
      </p>
      <p className="acc-metric win-metric">
        <span className="cp-n">01</span> {SITE.accuracyF1Label}
      </p>
      <p className="acc-calib">{SITE.accuracyCalibration}</p>
      <div className="win-cards win-f1">
        <div className="win-card ours">
          <p className="win-who">PayCheck</p>
          <p className="win-big">
            <CountUp to={Number(SITE.accuracyF1.paycheck)} decimals={2} start={inView} />
          </p>
        </div>
        <div className="win-card">
          <p className="win-who">Claude Haiku 5.5</p>
          <p className="win-big">
            <CountUp to={Number(SITE.accuracyF1.haiku)} decimals={2} start={inView} />
          </p>
        </div>
      </div>
      <p className="acc-metric win-metric">
        <span className="cp-n">02</span> Honest pages wrongly blocked (300-page benchmark)
      </p>
      <div className="win-cards">
        <div className="win-card ours">
          <p className="win-who">PayCheck</p>
          <p className="win-big">
            <CountUp to={0} start={inView} />
            <span className="win-of"> of {HONEST}</span>
          </p>
          <PageGrid red={false} />
          <Tag verdict="cleared" className="win-stamp" />
        </div>
        <div className="win-card">
          <p className="win-who">Claude Haiku 5.5</p>
          <p className="win-big">
            <CountUp to={HAIKU_FALSE} start={inView} />
            <span className="win-of"> of {HONEST}</span>
          </p>
          <PageGrid red />
          <Tag verdict="held" className="win-count" />
        </div>
      </div>
    </figure>
  );
}


const FULL_ROWS: { id: string; name: string }[] = [
  { id: "guard", name: "PayCheck" },
  { id: "claude-haiku", name: "Claude Haiku 5.5" },
  { id: "qwen-base", name: "Qwen3-4B before training" },
];

export function FullResults({ models }: { models: ModelEval[] }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const rows = FULL_ROWS.map((row) => ({ ...row, model: models.find((m) => m.id === row.id) })).filter((row) => row.model);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  useEffect(() => {
    const fromHash = () => setOpen(window.location.hash === "#full-results");
    fromHash();
    window.addEventListener("hashchange", fromHash);
    return () => window.removeEventListener("hashchange", fromHash);
  }, []);

  if (!rows.length) return null;
  return (
    <>
      <a
        className="micro full-results-link"
        href="#full-results"
        onClick={(event) => {
          event.preventDefault();
          setOpen(true);
        }}
      >
        {SITE.fullResultsLink}
      </a>
      <dialog ref={ref} className="full-results" aria-labelledby="full-results-title" onClose={() => setOpen(false)}>
        <div className="full-results-head">
          <h2 id="full-results-title" className="h3">
            {SITE.fullResultsLink}
          </h2>
          <button type="button" className="full-results-close" onClick={() => setOpen(false)} aria-label="Close">
            Close
          </button>
        </div>
        <div className="table-scroll">
          <table className="data">
            <caption className="sr-only">Locked 300-page benchmark, one row per model</caption>
            <thead>
              <tr>
                <th>Model</th>
                <th>Honest pages wrongly blocked</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ id, name, model }) => (
                <tr key={id}>
                  <th scope="row">{name}</th>
                  <td className={id === "guard" ? "on" : undefined}>{model?.display?.false_blocks ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="micro caption">
          {SITE.accuracyFootnote}
        </p>
      </dialog>
    </>
  );
}

/**
 * Section 4, Why it's better: one compact band. Heading, then the stat tiles, each fact once, using only
 * approved numbers from lib/copy.ts (heroReasons, accuracyF1).
 * PayCheck's number bold off-white, Haiku's muted. Red stays reserved for tricks and money lost.
 */
const WHY_TILES: { k: string; ours: string; theirs: string; cap: string; note?: string }[] = [
  { k: "Safer", ours: "0", theirs: "16", cap: "honest checkouts wrongly blocked (of 150)" },
  { k: "Better", ours: SITE.accuracyF1.paycheck, theirs: SITE.accuracyF1.haiku, cap: "F1 score" },
];

export function WhyBetter({ models }: { models: ModelEval[] }) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  return (
    <div className="wrap">
      <section ref={ref} className={inView ? "section why why19 is-in" : "section why why19"} aria-labelledby="why-title">
        <Sign n="04" id="why-title">
          Why it's better
        </Sign>
        <h2 className="why19-h">{SITE.heroVerdict}</h2>
        <ul className="why19-tiles">
          {WHY_TILES.map((t, i) => (
            <li key={t.k} className="why19-tile" style={{ ["--i" as string]: i }}>
              <p className="why19-k">{t.k}</p>
              <p className="why19-n" aria-label={`PayCheck ${t.ours}, Claude Haiku 5.5 ${t.theirs}`}>
                <b>{t.ours}</b>
                <span className="why19-vs"> vs </span>
                <span className="why19-them">{t.theirs}</span>
              </p>
              <p className="why19-cap">{t.cap}</p>
              {t.note ? <p className="why19-note">{t.note}</p> : null}
            </li>
          ))}
        </ul>
        <p className="why19-key">PayCheck vs Claude Haiku 5.5</p>
        <FullResults models={models} />
      </section>
    </div>
  );
}

/** Section 6, How we trained it: the one-cycle loop. */
export function Trained() {
  return (
    <div className="wrap">
      <section className="section" aria-labelledby="trained-title">
        <Sign n="06" id="trained-title">
          How we trained it
        </Sign>
        <Pin vh={360} className="pin-pipeline pin-loop">
          {(progress) => (
            <div className="pl-wrap tl-wrap" id="how-built">
              <TrainingLoop progress={progress} />
            </div>
          )}
        </Pin>
      </section>
    </div>
  );
}

export function Speed() {
  return (
    <div className="wrap">
      <section className="section speed" aria-labelledby="speed-title">
        <h3 className="acc-metric win-metric speed-h" id="speed-title">
          <span className="cp-n">05</span> {SITE.speedTitle}
        </h3>
        <SpeedRace />
        <SpeedBars />
      </section>
    </div>
  );
}

/**
 * Race: one check per lane, each pulse runs for its real typical time (0.7 s vs 1.5 s), side by side, on a loop.
 * Bar length = time (scaled to the longest), so the shorter bar is the faster one; every pulse moves at the same speed.
 * Each bar ends in an always-visible name + time label. Decorative (aria-hidden); the numbers are the stats above.
 */
function SpeedRace() {
  const longest = Math.max(...SITE.speedStats.map((stat) => stat.typical));
  const cycle = longest + 1.1;
  // Per-lane keyframes: the pulse arrives at (typical / cycle) of the shared loop, so the timing is real.
  const css = SITE.speedStats
    .map((stat, i) => {
      const at = ((stat.typical / cycle) * 100).toFixed(2);
      return `@keyframes race-dot-${i}{0%{left:0;opacity:1}${at}%{left:100%;opacity:1}92%{left:100%;opacity:1}100%{left:100%;opacity:0}}
@keyframes race-fill-${i}{0%{transform:scaleX(0)}${at}%{transform:scaleX(1)}92%{transform:scaleX(1);opacity:1}100%{transform:scaleX(1);opacity:0}}
@keyframes race-end-${i}{0%,${at}%{opacity:0;scale:1.6}${(Number(at) + 4).toFixed(2)}%{opacity:1;scale:1}92%{opacity:1}100%{opacity:0}}`;
    })
    .join("\n");
  return (
    <div className="race" aria-hidden="true" style={{ ["--cycle" as string]: `${cycle}s` }}>
      <style>{css}</style>
      <p className="race-head">
        <span>Time per check · {SITE.speedTypicalLabel}</span>
        <span className="race-head-k">Shorter bar = faster</span>
      </p>
      {SITE.speedStats.map((stat, i) => (
        <div key={stat.who} className={stat.ours ? "race-lane ours" : "race-lane"} style={{ ["--lane" as string]: i, ["--len" as string]: (stat.typical / longest).toFixed(4) }}>
          <span className="race-track">
            <span className="race-fill" style={{ animationName: `race-fill-${i}` }} />
            <span className="race-dot" style={{ animationName: `race-dot-${i}` }} />
            <span className="race-end" style={{ animationName: `race-end-${i}` }}>
              ✓
            </span>
          </span>
          <span className="race-label">
            <span className="race-who">{stat.who}</span>
            <span className="race-time">
              {stat.typical.toFixed(1)} {SITE.speedUnit}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

/** Side-by-side bars for both speed stats, scaled to the slowest value shown. Decorative; the numbers are the stats. */
function SpeedBars() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  const max = Math.max(...SITE.speedStats.map((stat) => stat.slowest));
  const rows = [
    { k: SITE.speedSlowestLabel, key: "slowest" as const },
  ];
  return (
    <div ref={ref} className={inView ? "sbars is-in" : "sbars"}>
      {rows.map((row, r) => (
        <div key={row.key} className="sbars-group">
          <p className="sbars-k">{row.k}</p>
          {SITE.speedStats.map((stat, i) => (
            <div key={stat.who} className={stat.ours ? "sbar ours" : "sbar"}>
              <span className="sbar-who">{stat.who}</span>
              <span className="sbar-track">
                <span className="sbar-fill" style={{ width: `${(stat[row.key] / max) * 100}%`, ["--d" as string]: `${r * 220 + i * 110}ms` }} />
              </span>
              <span className="sbar-v">
                {stat[row.key].toFixed(1)} {SITE.speedUnit}
              </span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
