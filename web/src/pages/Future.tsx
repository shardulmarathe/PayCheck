import { motion } from "framer-motion";
import { SITE } from "../lib/copy";
import { Sign } from "../components/Sign";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import type { Dataset } from "../lib/types";

/** What's next (round 19): the existing items as a numbered roadmap row, animated in on scroll. No new claims. */
export function Future({ data: _data }: { data: Dataset }) {
  const reduced = usePrefersReducedMotion();
  const steps = [
    ...SITE.futureItems.map((body, i) => ({ title: SITE.futureTitles[i], body })),
    // One line each: the device item keeps its first sentence only (existing copy).
    { title: SITE.futureDevice.title, body: SITE.futureDevice.body.split(". ")[0] + "." },
  ];
  return (
    <div className="wrap">
      <section className="section road" aria-labelledby="future-title">
        <Sign n="07" id="future-title">
          {SITE.futureKicker}
        </Sign>
        <h2 className="road-h">{SITE.futureTitle}</h2>
        <ol className="road-row">
          {steps.map((s, i) => (
            <motion.li
              key={s.title}
              className="road-step"
              initial={reduced ? { opacity: 0 } : { opacity: 0, y: 18 }}
              whileInView={reduced ? { opacity: 1 } : { opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "0px 0px -10% 0px" }}
              transition={{ duration: reduced ? 0.3 : 0.5, delay: reduced ? 0 : i * 0.12, ease: [0.2, 0.8, 0.2, 1] }}
            >
              <span className="road-node" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </span>
              <h3 className="road-t">{s.title}</h3>
              <p className="road-b">{s.body}</p>
            </motion.li>
          ))}
        </ol>
      </section>
    </div>
  );
}
