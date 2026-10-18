import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { CountUp } from "../components/motion/CountUp";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { HERO_RESULT } from "../lib/copy";
import { DESCRIPTOR, PRODUCT_NAME, TAGLINE } from "../lib/product";
import type { Dataset } from "../lib/types";

/**
 * Section 2, Meet PayCheck: the big moment. A large centred wordmark inside checkpoint brackets with one entrance
 * (brackets close in, one scan line passes), the tagline, the descriptor, then the before/after bars and their scope.
 */
export function Demo({ data: _data }: { data: Dataset }) {
  const ref = useRef<HTMLElement>(null);
  const shown = useInView(ref, { once: true, margin: "0px 0px -25% 0px" });
  const reduced = usePrefersReducedMotion();
  const on = shown || reduced;
  const enter = (d: number) => ({
    initial: false as const,
    animate: { opacity: on ? 1 : 0, y: on || reduced ? 0 : 16 },
    transition: { duration: reduced ? 0 : 0.6, delay: reduced ? 0 : d, ease: [0.2, 0.8, 0.2, 1] as const },
  });
  return (
    <div className="wrap">
      <section ref={ref} className={on ? "section meet is-in" : "section meet"} aria-labelledby="meet-title">
        <div className="meet-mark">
          <span className="meet-brk" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
          {reduced ? null : <span className="meet-scan" aria-hidden="true" />}
          <motion.h2 id="meet-title" className="meet-word" {...enter(0.15)}>
            {PRODUCT_NAME}
          </motion.h2>
        </div>
        <motion.p className="meet-tag" {...enter(0.55)}>
          {TAGLINE}
        </motion.p>
        <motion.p className="meet-desc" {...enter(0.7)}>
          {DESCRIPTOR.charAt(0).toUpperCase() + DESCRIPTOR.slice(1)}.
        </motion.p>
        <motion.div className="hero-result meet-result" {...enter(0.9)}>
          <p className="hero-result-line">{HERO_RESULT.line}</p>
          <div className="hero-bars" aria-hidden="true">
            {HERO_RESULT.bars.map((b) => (
              <div key={b.label} className={`hero-bar is-${b.tone}`}>
                <span className="hero-bar-l">{b.label}</span>
                <span className="hero-bar-track">
                  <span className="hero-bar-fill" style={{ transform: `scaleX(${on ? b.n / b.of : 0})`, transitionDelay: reduced ? "0ms" : "1100ms" }} />
                </span>
                <span className="hero-bar-n">
                  <CountUp to={b.n} start={on} /> of {b.of}
                </span>
              </div>
            ))}
          </div>
          <p className="hero-result-scope">{HERO_RESULT.scope}</p>
        </motion.div>
      </section>
    </div>
  );
}
