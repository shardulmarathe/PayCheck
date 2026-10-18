import { motion } from "framer-motion";
import { EVIDENCE } from "../lib/copy";
import { CountUp } from "./motion/CountUp";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { INCIDENTS, SIMULATIONS, type Incident } from "../data/incidents";

/**
 * Section 1, The problem: compact, about one screen. One headline, one short line, then the
 * sources as small chips (name · date · a few words), each linking to its source; hover/focus shows the full line and
 * quote. One stat as a small line (76% of 642, FTC). Chip copy: data/incidents.ts. Stat: lib/copy.ts EVIDENCE.bigStats.
 */
const CHIP_NAME: Record<string, string> = { "Microsoft Magentic Marketplace": "Microsoft Magentic" };

export function Evidence() {
  const reduced = usePrefersReducedMotion();
  const chips: Incident[] = [...INCIDENTS, ...SIMULATIONS];
  const stat = EVIDENCE.bigStats.find((s) => s.kind === "count" && s.to === 76);
  return (
    <div className="wrap">
      <section className="ev ev18" aria-labelledby="evidence-title">
        <p className="cp-sign ev-sign">
          <span className="cp-sign-n">{EVIDENCE.kicker}</span>
        </p>
        <h1 id="evidence-title" className="h1 ev-title">
          {EVIDENCE.title}
        </h1>
        <p className="ev18-line">It has already happened with real shoppers, and security researchers can make it happen on purpose.</p>
        <ul className="ev-chips">
          {chips.map((c, i) => (
            <motion.li
              key={c.name}
              initial={reduced ? { opacity: 0 } : { opacity: 0, y: 16 }}
              whileInView={reduced ? { opacity: 1 } : { opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "0px 0px -8% 0px" }}
              transition={{ duration: reduced ? 0.3 : 0.45, delay: reduced ? 0 : 0.15 + i * 0.06, ease: [0.2, 0.8, 0.2, 1] }}
            >
              <a className="ev-chip" href={c.links[0].href} target="_blank" rel="noopener noreferrer">
                <span className="ev-chip-top">
                  <b>{CHIP_NAME[c.name] ?? c.name}</b> · {c.date}
                </span>
                <span className="ev-chip-w">{c.chip}</span>
                <span className="ev-chip-more" role="tooltip">
                  {c.body} <q>{c.quote}</q> <em>{c.sourceLine}</em>
                </span>
              </a>
            </motion.li>
          ))}
        </ul>
        {stat && stat.kind === "count" ? (
          <p className="ev18-stat">
            {stat.label.split("76%")[0]}
            <b className="ev18-n">
              <CountUp to={76} start duration={1.2} />%
            </b>
            {stat.label.split("76%")[1]}{" "}
            <a href={stat.href} target="_blank" rel="noopener noreferrer">
              {stat.source}
            </a>
          </p>
        ) : null}
      </section>
    </div>
  );
}
