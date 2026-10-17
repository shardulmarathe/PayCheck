import { animate, motion, useInView, useMotionValue, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { EASE } from "../lib/ease";
import { useNav } from "./motion/Nav";

const SPOTS = [
  { t: 0.88, align: "left" },
  { t: 0.12, align: "right" },
  { t: 0.5, align: "below" },
] as const;

function scoreLabel(score: number | null): string {
  if (score == null || !Number.isFinite(score)) return "[X]%";
  const text = Number.isInteger(score) ? String(score) : String(Math.round(score * 10) / 10);
  return `${text}%`;
}

function roundLabel(round: number | null): string {
  if (round == null || !Number.isFinite(round)) return "ROUND r[n]";
  return `ROUND r${round}`;
}

export function LoopDiagram({
  nodes,
  round,
  score,
  caption,
}: {
  nodes: { n: string; title: string; detail: string }[];
  round: number | null;
  score: number | null;
  caption: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  const reduced = usePrefersReducedMotion();
  const { isGliding } = useNav();
  const progress = useMotionValue(reduced ? 1 : 0);
  const lit = reduced || isGliding || inView;
  const shown = nodes.slice(0, SPOTS.length);
  useEffect(() => {
    if (reduced || isGliding) {
      progress.set(1);
      return;
    }
    if (!inView) return;
    const controls = animate(progress, 1, { duration: 1.6, delay: shown.length * 0.12, ease: EASE });
    return () => controls.stop();
  }, [inView, reduced, isGliding, progress, shown.length]);
  const cx = 500;
  const cy = 250;
  const rx = 300;
  const ry = 118;
  const dotX = useTransform(progress, (value) => cx + rx * Math.sin(value * Math.PI * 2));
  const dotY = useTransform(progress, (value) => cy - ry * Math.cos(value * Math.PI * 2));

  return (
    <div className="loop-v3" ref={ref}>
      <div className="loop-stage">
        <svg className="loop-floor" viewBox="0 0 1000 520" aria-hidden="true">
          <ellipse cx={cx} cy={cy} rx="360" ry="168" fill="#11141A" />
          <ellipse data-loop-ring="" cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#323A45" strokeWidth="1.5" />
          {SPOTS.map((spot, index) => {
            const angle = spot.t * Math.PI * 2;
            const x = cx + rx * Math.sin(angle);
            const y = cy - ry * Math.cos(angle);
            const stem = spot.align === "below" ? 36 : -36;
            return (
              <g key={shown[index]?.n ?? index}>
                <line x1={x} y1={y} x2={x} y2={y + stem} stroke="#EEF1F5" strokeWidth="1" />
                <circle cx={x} cy={y} r="4" fill="#EEF1F5" />
              </g>
            );
          })}
          {reduced ? <circle cx={cx} cy={cy - ry} r="5" fill="#EEF1F5" /> : <motion.circle cx={dotX} cy={dotY} r="5" fill="#EEF1F5" />}
        </svg>
        <div className="loop-center">
          <p className="loop-round">{roundLabel(round)}</p>
          <p className="loop-pct">{scoreLabel(score)}</p>
          <p className="micro">{caption}</p>
        </div>
        <div className="loop-labels">
          {shown.map((node, index) => {
            const spot = SPOTS[index];
            if (!spot) return null;
            const angle = spot.t * Math.PI * 2;
            const x = cx + rx * Math.sin(angle);
            const y = cy - ry * Math.cos(angle);
            return (
              <motion.div
                key={node.n}
                className={`loop-label ${spot.align}`}
                data-loop-last={index === shown.length - 1 ? "" : undefined}
                initial={false}
                animate={{ opacity: lit ? 1 : 0 }}
                transition={{ duration: reduced || isGliding ? 0 : 0.25, delay: reduced || isGliding ? 0 : index * 0.12, ease: EASE }}
                style={{ left: `${(x / 1000) * 100}%`, top: `${(y / 520) * 100}%` }}
              >
                <p>
                  {node.n} {node.title}
                </p>
                <p className="micro">{node.detail}</p>
              </motion.div>
            );
          })}
        </div>
      </div>
      <ol className="node-list">
        {shown.map((node) => (
          <li key={node.n}>
            <p className="micro">{node.n}</p>
            <h3 className="title">{node.title}</h3>
            <p className="micro">{node.detail}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
