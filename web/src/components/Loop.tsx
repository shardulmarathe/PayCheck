import { animate, useInView, useMotionValue, useTransform, motion } from "framer-motion";
import { useEffect, useRef } from "react";
import { EASE } from "../lib/ease";
import { usePrefersReducedMotion } from "../hooks/useReplay";

export function LoopDiagram({
  nodes,
  roundLabel,
  caught,
  caption,
  example,
}: {
  nodes: { n: string; title: string; detail: string; place: "top" | "right" | "bottom" | "left" }[];
  roundLabel: string;
  caught: number;
  caption: string;
  example: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const reduced = usePrefersReducedMotion();
  const progress = useMotionValue(0);
  useEffect(() => {
    if (!inView || reduced) return;
    const controls = animate(progress, 1, { duration: 1.2, ease: EASE });
    return () => controls.stop();
  }, [inView, reduced, progress]);
  const cx = useTransform(progress, (value) => 180 + 158 * Math.sin(value * Math.PI * 2));
  const cy = useTransform(progress, (value) => 180 - 158 * Math.cos(value * Math.PI * 2));

  return (
    <div className="loop" ref={ref}>
      <svg className="loop-svg" viewBox="0 0 360 360" aria-hidden="true">
        <circle cx="180" cy="180" r="158" fill="none" stroke="#323A45" strokeWidth="1" />
        {[0, 90, 180, 270].map((deg) => {
          const rad = (deg * Math.PI) / 180;
          const x = 180 + 158 * Math.sin(rad);
          const y = 180 - 158 * Math.cos(rad);
          const tx = Math.cos(rad);
          const ty = Math.sin(rad);
          return <line key={deg} x1={x} y1={y} x2={x + tx * 14} y2={y + ty * 14} stroke="#EEF1F5" strokeWidth="1" />;
        })}
        {[0, 90, 180, 270].map((deg) => {
          const rad = (deg * Math.PI) / 180;
          return <circle key={`dot-${deg}`} cx={180 + 158 * Math.sin(rad)} cy={180 - 158 * Math.cos(rad)} r="4" fill="#EEF1F5" />;
        })}
        {reduced ? <circle cx="180" cy="22" r="4" fill="#EEF1F5" /> : <motion.circle cx={cx} cy={cy} r="4" fill="#EEF1F5" />}
      </svg>
      <div className="loop-center">
        <p className="label">{roundLabel}</p>
        <p className="loop-pct">{caught}%</p>
        <p className="micro">
          {caption}
          {example ? " · example data" : ""}
        </p>
      </div>
      <div className="loop-nodes">
        {nodes.map((node) => (
          <div key={node.n} className={`node ${node.place}`}>
            <p className="micro">{node.n}</p>
            <h3>{node.title}</h3>
            <p className="micro">{node.detail}</p>
          </div>
        ))}
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
