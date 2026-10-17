import { animate, motion, useInView, useMotionValue, useTransform } from "framer-motion";
import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { EASE } from "../lib/ease";

const SPOTS = [
  { t: 0.875, stem: "up" },
  { t: 0.125, stem: "up" },
  { t: 0.375, stem: "down" },
  { t: 0.625, stem: "down" },
] as const;

export function LoopDiagram({
  nodes,
  roundLabel,
  caught,
  caption,
  example,
}: {
  nodes: { n: string; title: string; detail: string; place: "top" | "right" | "bottom" | "left" }[];
  roundLabel: string;
  caught: number | null;
  caption: string;
  example: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const reduced = usePrefersReducedMotion();
  const progress = useMotionValue(reduced ? 0 : 0);
  useEffect(() => {
    if (!inView || reduced) return;
    const controls = animate(progress, 1, { duration: 2.6, ease: EASE });
    return () => controls.stop();
  }, [inView, reduced, progress]);
  const cx = 500;
  const cy = 250;
  const rx = 300;
  const ry = 118;
  const dotX = useTransform(progress, (value) => cx + rx * Math.sin(value * Math.PI * 2));
  const dotY = useTransform(progress, (value) => cy - ry * Math.cos(value * Math.PI * 2));

  return (
    <div className="loop-v3" ref={ref}>
      <svg className="loop-floor" viewBox="0 0 1000 520" aria-hidden="true">
        <ellipse cx={cx} cy={cy} rx="360" ry="168" fill="#11141A" />
        <ellipse cx={cx} cy={cy} rx={rx} ry={ry} fill="none" stroke="#323A45" strokeWidth="1.5" />
        {SPOTS.map((spot, index) => {
          const angle = spot.t * Math.PI * 2;
          const x = cx + rx * Math.sin(angle);
          const y = cy - ry * Math.cos(angle);
          const stem = spot.stem === "up" ? -36 : 36;
          return (
            <g key={nodes[index]?.n ?? index}>
              <line x1={x} y1={y} x2={x} y2={y + stem} stroke="#EEF1F5" strokeWidth="1" />
              <circle cx={x} cy={y} r="4" fill="#EEF1F5" />
            </g>
          );
        })}
        {reduced ? <circle cx={cx} cy={cy - ry} r="5" fill="#EEF1F5" /> : <motion.circle cx={dotX} cy={dotY} r="5" fill="#EEF1F5" />}
      </svg>
      <div className="loop-center">
        {caught != null ? (
          <>
            <p className="label">{roundLabel}</p>
            <p className="loop-pct">{caught}%</p>
            <p className="micro">
              {caption}
              {example ? " · example data" : ""}
            </p>
          </>
        ) : null}
      </div>
      <div className="loop-labels">
        {nodes.map((node, index) => {
          const spot = SPOTS[index];
          if (!spot) return null;
          const angle = spot.t * Math.PI * 2;
          const x = cx + rx * Math.sin(angle);
          const y = cy - ry * Math.cos(angle);
          const labelY = spot.stem === "up" ? y - 86 : y + 52;
          return (
            <div
              key={node.n}
              className={`loop-label ${spot.stem}`}
              style={{ left: `${(x / 1000) * 100}%`, top: `${(labelY / 520) * 100}%` }}
            >
              <p>
                {node.n} {node.title}
              </p>
              <p className="micro">{node.detail}</p>
            </div>
          );
        })}
      </div>
      <ol className="node-list">
        {nodes.map((node) => (
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
