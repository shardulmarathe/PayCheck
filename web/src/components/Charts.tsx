import { motion, useInView } from "framer-motion";
import { useId, useRef } from "react";
import { EASE } from "../lib/ease";
import { formatMs, formatPct, roundLabel, trimNum } from "../lib/format";
import type { ModelEval, TrainingRound } from "../lib/types";
import { usePrefersReducedMotion } from "../hooks/useReplay";

function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });
  const reduced = usePrefersReducedMotion();
  return { ref, reveal: reduced || inView, reduced };
}

function xAt(index: number, count: number): number {
  const pad = 8;
  if (count <= 1) return 50;
  return pad + (index / (count - 1)) * (100 - pad * 2);
}

function yAt(value: number): number {
  return 8 + (1 - value / 100) * 80;
}

export function TrainingChart({
  rounds,
  seenLabel,
  heldLabel,
}: {
  rounds: TrainingRound[];
  seenLabel: string;
  heldLabel: string;
}) {
  const { ref, reveal, reduced } = useReveal();
  const clipId = useId().replace(/:/g, "");
  const seen = rounds.map((round) => round.catch_seen);
  const held = rounds.map((round) => round.catch_heldout);
  const line = (values: number[]) => values.map((value, index) => `${index === 0 ? "M" : "L"} ${xAt(index, values.length)} ${yAt(value)}`).join(" ");
  return (
    <div ref={ref}>
      <div className="plot-frame" aria-hidden="true">
        <div className="plot">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none">
            <defs>
              <clipPath id={clipId}>
                <motion.rect
                  y="0"
                  height="100"
                  initial={false}
                  animate={{ width: reveal ? 100 : 0 }}
                  transition={{ duration: reduced ? 0 : 1.2, ease: EASE }}
                />
              </clipPath>
            </defs>
            {[0, 25, 50, 75, 100].map((mark) => (
              <line
                key={mark}
                x1="0"
                x2="100"
                y1={yAt(mark)}
                y2={yAt(mark)}
                stroke="#232932"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <path d={line(seen)} fill="none" stroke="#EEF1F5" strokeWidth="1.5" vectorEffect="non-scaling-stroke" clipPath={`url(#${clipId})`} />
            <path
              d={line(held)}
              fill="none"
              stroke="#9AA3AE"
              strokeWidth="1.5"
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
              clipPath={`url(#${clipId})`}
            />
          </svg>
          {rounds.map((round, index) => (
            <span key={round.round}>
              <motion.i
                className="plot-dot"
                style={{ left: `${xAt(index, rounds.length)}%`, top: `${yAt(round.catch_seen)}%` }}
                initial={{ opacity: reduced ? 1 : 0 }}
                animate={{ opacity: reveal ? 1 : 0 }}
                transition={{ duration: reduced ? 0 : 0.5, delay: reduced ? 0 : 1.05, ease: EASE }}
              />
              <motion.i
                className="plot-dot held"
                style={{ left: `${xAt(index, rounds.length)}%`, top: `${yAt(round.catch_heldout)}%` }}
                initial={{ opacity: reduced ? 1 : 0 }}
                animate={{ opacity: reveal ? 1 : 0 }}
                transition={{ duration: reduced ? 0 : 0.5, delay: reduced ? 0 : 1.05, ease: EASE }}
              />
              {rounds.length <= 6 ? (
                <span className="plot-label" style={{ left: `${xAt(index, rounds.length)}%`, top: `${yAt(round.catch_seen)}%` }}>
                  {trimNum(round.catch_seen)}%
                </span>
              ) : null}
            </span>
          ))}
        </div>
        <div className="axis-row">
          {rounds.map((round) => (
            <span key={round.round} className="micro">
              {roundLabel(round.round)}
            </span>
          ))}
        </div>
        <div className="legend">
          <span className="micro">
            <i className="swatch" />
            {seenLabel}
          </span>
          <span className="micro">
            <i className="swatch dashed" />
            {heldLabel}
          </span>
        </div>
      </div>
      <table className="sr-only">
        <caption>Catch rate by training round, percent</caption>
        <thead>
          <tr>
            <th>Round</th>
            <th>{seenLabel}</th>
            <th>{heldLabel}</th>
          </tr>
        </thead>
        <tbody>
          {rounds.map((round) => (
            <tr key={round.round}>
              <th>{roundLabel(round.round)}</th>
              <td>{trimNum(round.catch_seen)}%</td>
              <td>{trimNum(round.catch_heldout)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Small catch-rate line under the cost chart. One series. Red is only the last point. */
export function RoundCatchChart({ rounds }: { rounds: TrainingRound[] }) {
  const { ref, reveal, reduced } = useReveal();
  const clipId = useId().replace(/:/g, "");
  const values = rounds.map((round) => round.catch_seen);
  const line = values.map((value, index) => `${index === 0 ? "M" : "L"} ${xAt(index, values.length)} ${yAt(value)}`).join(" ");
  const last = rounds.length - 1;
  return (
    <div ref={ref}>
      <div className="plot-frame" aria-hidden="true">
        <div className="plot compact">
          <svg viewBox="0 0 100 100" preserveAspectRatio="none">
            <defs>
              <clipPath id={clipId}>
                <motion.rect
                  y="0"
                  height="100"
                  initial={false}
                  animate={{ width: reveal ? 100 : 0 }}
                  transition={{ duration: reduced ? 0 : 1.2, ease: EASE }}
                />
              </clipPath>
            </defs>
            {[0, 50, 100].map((mark) => (
              <line
                key={mark}
                x1="0"
                x2="100"
                y1={yAt(mark)}
                y2={yAt(mark)}
                stroke="#232932"
                strokeWidth="1"
                vectorEffect="non-scaling-stroke"
              />
            ))}
            <path d={line} fill="none" stroke="#EEF1F5" strokeWidth="1" vectorEffect="non-scaling-stroke" clipPath={`url(#${clipId})`} />
          </svg>
          {rounds.map((round, index) => (
            <span key={round.round}>
              <motion.i
                className={index === last ? "plot-dot final" : "plot-dot"}
                style={{ left: `${xAt(index, rounds.length)}%`, top: `${yAt(round.catch_seen)}%` }}
                initial={{ opacity: reduced ? 1 : 0 }}
                animate={{ opacity: reveal ? 1 : 0 }}
                transition={{ duration: reduced ? 0 : 0.5, delay: reduced ? 0 : 1.05, ease: EASE }}
              />
              {index === last ? (
                <span className="plot-label" style={{ left: `${xAt(index, rounds.length)}%`, top: `${yAt(round.catch_seen)}%` }}>
                  {trimNum(round.catch_seen)}%
                </span>
              ) : null}
            </span>
          ))}
        </div>
        <div className="axis-row">
          {rounds.map((round) => (
            <span key={round.round} className="micro">
              {roundLabel(round.round)}
            </span>
          ))}
        </div>
      </div>
      <table className="sr-only">
        <caption>Catch rate by training round, percent</caption>
        <thead>
          <tr>
            <th>Round</th>
            <th>Catch rate</th>
          </tr>
        </thead>
        <tbody>
          {rounds.map((round) => (
            <tr key={round.round}>
              <th>{roundLabel(round.round)}</th>
              <td>{trimNum(round.catch_seen)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const LAT_MIN = 10;
const LAT_MAX = 10000;

function latWidth(ms: number): number {
  const p = (Math.log10(ms) - Math.log10(LAT_MIN)) / (Math.log10(LAT_MAX) - Math.log10(LAT_MIN));
  return Math.min(100, Math.max(4, p * 100));
}

export function LatencyChart({ models, note }: { models: ModelEval[]; note: string }) {
  const { ref, reveal, reduced } = useReveal();
  const ordered = [...models].sort((a, b) => Number(b.emphasis) - Number(a.emphasis) || a.latency_ms_median - b.latency_ms_median);
  return (
    <div ref={ref}>
      <div className="bars" aria-hidden="true">
        {ordered.map((model) => (
          <div key={model.id} className="bar-row">
            <p>{model.model}</p>
            <p className="bar-value">{formatMs(model.latency_ms_median)}</p>
            <div className="bar-track">
              <motion.span
                className={model.emphasis ? "bar-fill on" : "bar-fill"}
                initial={{ width: reduced ? `${latWidth(model.latency_ms_median)}%` : 0 }}
                animate={{ width: reveal ? `${latWidth(model.latency_ms_median)}%` : 0 }}
                transition={{ duration: reduced ? 0 : 1.2, ease: EASE }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="micro caption">{note}</p>
      <table className="sr-only">
        <caption>Median latency per check, milliseconds, log scale, lower is better</caption>
        <tbody>
          {ordered.map((model) => (
            <tr key={model.id}>
              <th>{model.model}</th>
              <td>{formatMs(model.latency_ms_median)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type Slice = "300" | "100";

function logX(cost: number): number {
  const min = Math.log10(0.01);
  const max = Math.log10(100);
  return ((Math.log10(Math.min(100, Math.max(0.01, cost))) - min) / (max - min)) * 100;
}

function catchY(rate: number): number {
  const clamped = Math.min(100, Math.max(20, rate));
  return ((100 - clamped) / 80) * 100;
}

export function pointFor(model: ModelEval, slice: Slice): { rate: number; hollow: boolean } | null {
  if (slice === "300") {
    if (model.catch_rate_300 != null) return { rate: model.catch_rate_300, hollow: false };
    if (model.catch_rate_100 != null) return { rate: model.catch_rate_100, hollow: true };
    return null;
  }
  if (model.catch_rate_100 != null) return { rate: model.catch_rate_100, hollow: false };
  return null;
}

export function CostScatter({
  models,
  slice,
  annotation,
}: {
  models: ModelEval[];
  slice: Slice;
  annotation: string;
}) {
  const { ref, reveal, reduced } = useReveal();
  const plotted = models
    .map((model) => {
      const point = pointFor(model, slice);
      return point ? { model, ...point } : null;
    })
    .filter((point): point is { model: ModelEval; rate: number; hollow: boolean } => !!point);
  const guard = plotted.find((point) => point.model.emphasis);
  const gemini = plotted.find((point) => /gemini/i.test(point.model.model));
  const marks = [0.01, 0.1, 1, 10, 100];
  return (
    <div ref={ref}>
      <div className="scatter" aria-hidden="true">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
          {[20, 40, 60, 80, 100].map((mark) => (
            <line
              key={mark}
              x1="0"
              x2="100"
              y1={catchY(mark)}
              y2={catchY(mark)}
              stroke="#232932"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {marks.map((mark) => (
            <line
              key={mark}
              y1="0"
              y2="100"
              x1={logX(mark)}
              x2={logX(mark)}
              stroke="#232932"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
        {plotted.map((point) => {
          const left = logX(point.model.cost_per_1k_checks_usd);
          const top = catchY(point.rate);
          const side = left > 72 ? "left" : "";
          return (
            <motion.div
              key={point.model.id}
              initial={{ opacity: reduced ? 1 : 0 }}
              animate={{ opacity: reveal ? 1 : 0 }}
              transition={{ duration: reduced ? 0 : 0.6, delay: reduced ? 0 : 0.8, ease: EASE }}
            >
              <span
                className={`scatter-point ${point.model.emphasis ? "lg" : "md"} ${point.hollow ? "hollow" : ""}`}
                style={{ left: `${left}%`, top: `${top}%` }}
              />
              <span className={`scatter-label ${side}`} style={{ left: `${left}%`, top: `${top}%` }}>
                <strong>{point.model.model}</strong>
                <span>
                  {formatPct(point.rate)} · {point.hollow ? "100 pages only" : `${slice === "100" ? "100" : point.model.pages} pages`}
                </span>
              </span>
            </motion.div>
          );
        })}
        {guard && gemini ? (
          <div
            className="annotation"
            style={{
              left: `${Math.min(logX(guard.model.cost_per_1k_checks_usd), logX(gemini.model.cost_per_1k_checks_usd))}%`,
              width: `${Math.abs(logX(guard.model.cost_per_1k_checks_usd) - logX(gemini.model.cost_per_1k_checks_usd))}%`,
              top: "8%",
            }}
          >
            <span>{annotation}</span>
          </div>
        ) : null}
      </div>
      <div className="axis-row">
        {marks.map((mark) => (
          <span key={mark} className="micro">
            {mark < 1 ? `$${mark}` : `$${mark}`}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>Catch rate against cost per 1,000 checks</caption>
        <thead>
          <tr>
            <th>Model</th>
            <th>Catch rate</th>
            <th>Cost per 1,000 checks</th>
            <th>Slice</th>
          </tr>
        </thead>
        <tbody>
          {plotted.map((point) => (
            <tr key={point.model.id}>
              <th>{point.model.model}</th>
              <td>{formatPct(point.rate)}</td>
              <td>${point.model.cost_per_1k_checks_usd}</td>
              <td>{point.hollow ? "100-page slice only" : `${slice}-page`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
