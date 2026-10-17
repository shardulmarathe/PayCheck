import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { useNav } from "./motion/Nav";
import { EASE } from "../lib/ease";
import { ENTER, STAGGER } from "../lib/motion";
import { formatPct, trimNum } from "../lib/format";
import type { ModelEval } from "../lib/types";

function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  const reduced = usePrefersReducedMotion();
  const { isGliding } = useNav();
  return { ref, reveal: reduced || isGliding || inView, reduced };
}

function logX(cost: number): number {
  const min = Math.log10(0.01);
  const max = Math.log10(100);
  return ((Math.log10(Math.min(100, Math.max(0.01, cost))) - min) / (max - min)) * 100;
}

/** Catch rate mapped onto a 40–100 axis. Values under 40 sit on the floor. */
function catchY(rate: number): number {
  const clamped = Math.min(100, Math.max(40, rate));
  return ((100 - clamped) / 60) * 100;
}

/** Unclamped axis position, so a confidence interval can cross the 40 line. */
function catchYRaw(rate: number): number {
  return ((100 - rate) / 60) * 100;
}

function pointLabel(model: ModelEval): { title: string; detail: string } {
  const rate = formatPct(model.catch_rate);
  if (model.emphasis) return { title: model.model, detail: `${rate} · ${model.pages} pages` };
  if (model.pages < 300 && model.catch_rate_100 != null) {
    return { title: `${model.model} · ${rate} · 100-page slice`, detail: "" };
  }
  return { title: `${model.model} · ${rate}`, detail: "" };
}

export function CostScatter({
  models,
  gap,
  costAxis,
}: {
  models: ModelEval[];
  gap: string | null;
  costAxis: string;
}) {
  const { ref, reveal, reduced } = useReveal();
  const guard = models.find((model) => model.emphasis);
  const claude = models.find((model) => model.id === "claude" || /claude/i.test(model.model));
  const marks = [0.01, 0.1, 1, 10, 100];
  const yMarks = [100, 80, 60, 40];
  return (
    <div ref={ref}>
      <div className="scatter" aria-hidden="true">
        <div className="y-axis">
          {yMarks.map((mark) => (
            <span key={mark} style={{ top: `${catchY(mark)}%` }}>
              {mark}%
            </span>
          ))}
        </div>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
          {yMarks.map((mark, index) => (
            <line
              key={mark}
              x1="0"
              x2="100"
              y1={catchY(mark)}
              y2={catchY(mark)}
              stroke="#232932"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
              pathLength={1}
              strokeDasharray={1}
              strokeDashoffset={reveal && !reduced ? 0 : 1}
              style={{ transition: `stroke-dashoffset ${reduced ? 0 : ENTER}s cubic-bezier(${EASE.join(",")}) ${index * STAGGER}s` }}
            />
          ))}
          {marks.map((mark, index) => (
            <line
              key={mark}
              y1="0"
              y2="100"
              x1={logX(mark)}
              x2={logX(mark)}
              stroke="#232932"
              strokeWidth="1"
              vectorEffect="non-scaling-stroke"
              pathLength={1}
              strokeDasharray={1}
              strokeDashoffset={reveal && !reduced ? 0 : 1}
              style={{ transition: `stroke-dashoffset ${reduced ? 0 : ENTER}s cubic-bezier(${EASE.join(",")}) ${(index + yMarks.length) * STAGGER}s` }}
            />
          ))}
        </svg>
        {models.map((model) => {
          if (model.ci_low == null || model.ci_high == null) return null;
          return (
            <span key={`${model.id}-ci-x`} className="ci-bar" style={{ left: `${logX(model.cost_per_1k_checks_usd)}%`, top: `${catchYRaw(Math.max(model.ci_low, model.ci_high))}%`, height: `${Math.abs(catchYRaw(model.ci_low) - catchYRaw(model.ci_high))}%` }}>
              <i className="ci-cap" />
              <i className="ci-stem" />
              <i className="ci-cap bottom" />
            </span>
          );
        })}
        {guard && claude && gap ? (
          <div
            className="gap-line"
            style={{
              left: `${Math.min(logX(guard.cost_per_1k_checks_usd), logX(claude.cost_per_1k_checks_usd))}%`,
              width: `${Math.abs(logX(claude.cost_per_1k_checks_usd) - logX(guard.cost_per_1k_checks_usd))}%`,
              top: `${catchY(guard.catch_rate)}%`,
              transform: reveal && !reduced ? "scaleX(1)" : "scaleX(0)",
              transformOrigin: logX(claude.cost_per_1k_checks_usd) < logX(guard.cost_per_1k_checks_usd) ? "left center" : "right center",
              transition: `transform ${reduced ? 0 : 0.9}s cubic-bezier(${EASE.join(",")})`,
            }}
          >
            <span>{gap}</span>
          </div>
        ) : null}
        {models.map((model) => {
          const left = logX(model.cost_per_1k_checks_usd);
          const top = catchY(model.catch_rate);
          const hollow = model.catch_rate_300 == null && model.catch_rate_100 != null;
          const label = pointLabel(model);
          const place = model.emphasis ? "guard-label" : hollow ? "above" : top > 92 ? "low" : left > 82 ? "left" : "";
          return (
            <motion.div
              key={model.id}
              initial={{ opacity: reduced ? 1 : 0 }}
              animate={{ opacity: reveal ? 1 : 0 }}
              transition={{ duration: reduced ? 0 : ENTER, ease: EASE }}
            >
              <span
                className={`scatter-point ${model.emphasis ? "guard" : "sm"} ${hollow ? "hollow" : ""}`}
                data-guard-dot={model.emphasis ? "" : undefined}
                style={{ left: `${left}%`, top: `${top}%` }}
              />
              <span className={`scatter-label ${place}`} style={{ left: `${left}%`, top: `${top}%` }}>
                <strong>{label.title}</strong>
                {label.detail ? <span>{label.detail}</span> : null}
              </span>
            </motion.div>
          );
        })}
      </div>
      <div className="scatter-foot">
        <div className="axis-row">
          {marks.map((mark) => (
            <span key={mark} className="micro">
              ${mark === 0.01 ? "0.01" : mark === 0.1 ? "0.10" : trimNum(mark)}
            </span>
          ))}
        </div>
        <div className="scatter-meta">
          <p className="label">Bars · 95% confidence interval</p>
          <p className="label">{costAxis}</p>
        </div>
      </div>
      <table className="sr-only">
        <caption>Catch rate against cost per 1,000 checks. The vertical axis runs from 40 to 100 percent. Each model includes a 95% confidence interval.</caption>
        <thead>
          <tr>
            <th>Model</th>
            <th>Catch rate</th>
            <th>95% CI low</th>
            <th>95% CI high</th>
            <th>Cost per 1,000 checks</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.id}>
              <th>{model.model}</th>
              <td>{formatPct(model.catch_rate)}</td>
              <td>{model.ci_low == null ? "—" : formatPct(model.ci_low)}</td>
              <td>{model.ci_high == null ? "—" : formatPct(model.ci_high)}</td>
              <td>${model.cost_per_1k_checks_usd}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
