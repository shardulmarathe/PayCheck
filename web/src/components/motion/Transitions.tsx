import { motion, useScroll, useTransform, type MotionValue } from "framer-motion";
import { useRef, type ReactNode } from "react";
import { usePrefersReducedMotion } from "../../hooks/useReplay";

/**
 * Round 17 section transitions (Shardul 8:20). Flat palette, no glow. Transform/opacity/clip-path only (compositor),
 * fixed heights (no layout shift). Reduced motion: no movement, simple fades or static.
 */

/** 1) Checkpoint gate: leaving the hero, two lane barrier arms swing open. Fixed 200px band. */
export function CheckpointGate() {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 0.95", "center 0.45"] });
  const left = useTransform(scrollYProgress, [0, 1], [0, -78]);
  const right = useTransform(scrollYProgress, [0, 1], [0, 78]);
  const lamp = useTransform(scrollYProgress, [0.6, 1], [0, 1]);
  return (
    <div ref={ref} className="gate" aria-hidden="true">
      <div className="gate-lane">
        <span className="gate-post is-l" />
        <motion.span className="gate-arm is-l" style={{ rotate: reduced ? -78 : left }}>
          {Array.from({ length: 7 }, (_, i) => (
            <i key={i} />
          ))}
        </motion.span>
        <motion.span className="gate-arm is-r" style={{ rotate: reduced ? 78 : right }}>
          {Array.from({ length: 7 }, (_, i) => (
            <i key={i} />
          ))}
        </motion.span>
        <span className="gate-post is-r" />
        <motion.span className="gate-sign" style={{ opacity: reduced ? 1 : lamp }}>
          Lane open
        </motion.span>
        <span className="gate-floor" />
      </div>
    </div>
  );
}

/**
 * 2) X-ray wipe: a crisp scan line sweeps down; above the line the content is in an x-ray state, below it normal.
 * Once the line reaches the bottom the x-ray lifts. Pass `progress` (0..1) to drive it from a pin; otherwise it
 * follows its own scroll position.
 */
export function XrayWipe({ children, progress, className }: { children: ReactNode; progress?: MotionValue<number> | null; className?: string }) {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const own = useScroll({ target: ref, offset: ["start 0.85", "start 0.05"] }).scrollYProgress;
  const p = progress ?? own;
  const clip = useTransform(p, (v) => `inset(0 0 ${(100 - Math.min(1, Math.max(0, v)) * 100).toFixed(2)}% 0)`);
  const lineY = useTransform(p, (v) => `${Math.min(1, Math.max(0, v)) * 100}%`);
  const veil = useTransform(p, [0, 0.02, 0.85, 1], [0, 1, 1, 0]);
  const line = useTransform(p, [0, 0.02, 0.96, 1], [0, 1, 1, 0]);
  return (
    <div ref={ref} className={className ? `xw ${className}` : "xw"}>
      {children}
      {reduced ? null : (
        <>
          <motion.span className="xw-veil" aria-hidden="true" style={{ clipPath: clip, opacity: veil }} />
          <motion.span className="xw-line" aria-hidden="true" style={{ top: lineY, opacity: line }} />
        </>
      )}
    </div>
  );
}

/** 3) Conveyor belt: content slides in from the side on a moving belt with animated tread lines. */
export function Belt({ children, from = "left", className }: { children: ReactNode; from?: "left" | "right"; className?: string }) {
  const reduced = usePrefersReducedMotion();
  const dx = from === "left" ? -90 : 90;
  return (
    <div className={className ? `belt ${className}` : "belt"}>
      <Tread dir={from} />
      <motion.div
        initial={reduced ? { opacity: 0 } : { opacity: 0, x: dx }}
        whileInView={reduced ? { opacity: 1 } : { opacity: 1, x: 0 }}
        viewport={{ once: true, margin: "0px 0px -12% 0px" }}
        transition={{ duration: reduced ? 0.4 : 0.9, ease: [0.2, 0.8, 0.2, 1] }}
      >
        {children}
      </motion.div>
    </div>
  );
}

/** The belt itself: a thin track whose tread lines march in the direction the content arrives from. */
export function Tread({ dir = "left" }: { dir?: "left" | "right" }) {
  return (
    <div className={`tread is-${dir}`} aria-hidden="true">
      <span className="tread-run">
        {Array.from({ length: 80 }, (_, i) => (
          <i key={i} />
        ))}
      </span>
      <b className="tread-roller is-a" />
      <b className="tread-roller is-b" />
    </div>
  );
}
