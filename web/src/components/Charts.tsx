import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { EASE } from "../lib/ease";
import { formatPct } from "../lib/format";
import type { ModelEval } from "../lib/types";

function useReveal() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.35 });
  const reduced = usePrefersReducedMotion();
  return { ref, reveal: reduced || inView, reduced };
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

function pointLabel(model: ModelEval): { title: string; detail: string } {
  const rate = formatPct(model.catch_rate);
  if (model.emphasis) return { title: model.model, detail: `${rate} · ${model.pages} pages` };
  if (model.pages < 300) return { title: model.model, detail: `${rate} · 100-page slice` };
  return { title: `${model.model} · ${rate}`, detail: "" };
}

export function CostScatter({ models, annotation }: { models: ModelEval[]; annotation: string }) {
  const { ref, reveal, reduced } = useReveal();
  const guard = models.find((model) => model.emphasis);
  const gemini = models.find((model) => model.id === "gemini" || /gemini/i.test(model.model));
  const marks = [0.01, 0.1, 1, 10, 100];
  const yMarks = [100, 80, 60, 40];
  return (
    <div ref={ref}>
      <div className="scatter" aria-hidden="true">
        <div className="y-axis">
          {yMarks.map((mark) => (
            <span key={mark} style={{ top: `${catchY(mark)}%` }}>
              {mark}
            </span>
          ))}
        </div>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
          {yMarks.map((mark) => (
            <line key={mark} x1="0" x2="100" y1={catchY(mark)} y2={catchY(mark)} stroke="#232932" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
          {marks.map((mark) => (
            <line key={mark} y1="0" y2="100" x1={logX(mark)} x2={logX(mark)} stroke="#232932" strokeWidth="1" vectorEffect="non-scaling-stroke" />
          ))}
        </svg>
        {models.map((model) => {
          const left = logX(model.cost_per_1k_checks_usd);
          const top = catchY(model.catch_rate);
          const hollow = model.catch_rate_300 == null && model.catch_rate_100 != null;
          const label = pointLabel(model);
          const side = left > 70 ? "left" : "";
          return (
            <motion.div
              key={model.id}
              initial={{ opacity: reduced ? 1 : 0 }}
              animate={{ opacity: reveal ? 1 : 0 }}
              transition={{ duration: reduced ? 0 : 0.6, ease: EASE }}
            >
              <span
                className={`scatter-point ${model.emphasis ? "guard" : "sm"} ${hollow ? "hollow" : ""}`}
                style={{ left: `${left}%`, top: `${top}%` }}
              />
              <span className={`scatter-label ${model.emphasis ? "guard-label" : ""} ${side}`} style={{ left: `${left}%`, top: `${top}%` }}>
                <strong>{label.title}</strong>
                {label.detail ? <span>{label.detail}</span> : null}
              </span>
            </motion.div>
          );
        })}
        {guard && gemini ? (
          <div
            className="gap-line"
            style={{
              left: `${logX(guard.cost_per_1k_checks_usd)}%`,
              width: `${logX(gemini.cost_per_1k_checks_usd) - logX(guard.cost_per_1k_checks_usd)}%`,
              top: `${catchY(guard.catch_rate)}%`,
            }}
          >
            <span>{annotation}</span>
            <i />
          </div>
        ) : null}
      </div>
      <div className="axis-row">
        {marks.map((mark) => (
          <span key={mark} className="micro">
            {mark === 0.01 ? "0.01" : mark === 0.1 ? "0.10" : mark}
          </span>
        ))}
      </div>
      <table className="sr-only">
        <caption>Catch rate against cost per 1,000 checks. The vertical axis runs from 40 to 100 percent.</caption>
        <thead>
          <tr>
            <th>Model</th>
            <th>Catch rate</th>
            <th>Cost per 1,000 checks</th>
          </tr>
        </thead>
        <tbody>
          {models.map((model) => (
            <tr key={model.id}>
              <th>{model.model}</th>
              <td>{formatPct(model.catch_rate)}</td>
              <td>${model.cost_per_1k_checks_usd}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
