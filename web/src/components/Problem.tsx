import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { EASE } from "../lib/ease";
import { PROBLEM_SOURCES } from "../lib/problemSources";
import { useNav } from "./motion/Nav";

const ROW = 0.12;
const FADE = 0.3;

const LINES = [
  {
    body: "On 55 real shopping sites seeded with dark patterns, a Browser Use agent running Gemini 2.5 Pro left a pre-checked paid add-on selected 87% of the time.",
    source: PROBLEM_SOURCES.susbench,
  },
  {
    body: "In an ACL 2026 benchmark, all five AI shopping agents tested checked out with a padded total every time they reached a checkout with one.",
    source: PROBLEM_SOURCES.webdecept,
  },
] as const;

export function Problem() {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -15% 0px" });
  const reduced = usePrefersReducedMotion();
  const { isGliding } = useNav();
  const settled = reduced || isGliding;
  const show = settled || inView;

  return (
    <section id="problem" className="section problem" ref={ref} aria-labelledby="problem-title">
      <div className="problem-lead">
        <div>
          <p className="label">The problem</p>
          <h2 id="problem-title" className="problem-title">
            Asked only to find cheap eggs, OpenAI’s Operator bought them, charged $31.43, and reported $19.68.
          </h2>
          <p className="problem-cite">{PROBLEM_SOURCES.operator}</p>
        </div>
        <div className="problem-receipt" aria-label="Charged $31.43, reported $19.68">
          <motion.div
            className="problem-receipt-row"
            initial={settled ? false : { opacity: 0 }}
            animate={{ opacity: show ? 1 : 0 }}
            transition={{ duration: 0 }}
          >
            <span className="problem-key">Charged</span>
            <span className="problem-amt loss">$31.43</span>
          </motion.div>
          <motion.div
            className="problem-receipt-row"
            initial={settled ? false : { opacity: 0 }}
            animate={{ opacity: show ? 1 : 0 }}
            transition={{ duration: 0, delay: settled || !show ? 0 : ROW }}
          >
            <span className="problem-key">Reported</span>
            <span className="problem-amt">$19.68</span>
          </motion.div>
        </div>
      </div>
      <hr className="problem-rule" />
      <div className="problem-split">
        {LINES.map((line) => (
          <motion.div
            key={line.source}
            initial={settled ? false : { opacity: 0 }}
            animate={{ opacity: show ? 1 : 0 }}
            transition={{ duration: settled ? 0 : FADE, delay: settled || !show ? 0 : ROW * 2, ease: EASE }}
          >
            <p className="problem-line">{line.body}</p>
            <p className="problem-cite">{line.source}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
