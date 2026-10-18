import { motion, useInView } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { Sign } from "./Sign";

/**
 * "Coach" prototype. NOT a shipped feature: labelled Prototype, illustration on a practice store.
 * Honesty: PayCheck judges the PAGE the agent is on at each step (it reads page text, not agent intent);
 * the agent's planned action is only displayed beside it. Trick names reuse the site's existing labels
 * (Protection plan add-on, Surprise final fee). No numbers.
 */
type Step = { page: string; action: string; verdict: "go" | "stop"; trick?: string; reason: string; tip: string };

const STEPS: Step[] = [
  { page: "Search results", action: "Search the store", verdict: "go", reason: "Ordinary search page, nothing asks for money.", tip: "Compare a few listings before picking one." },
  { page: "Product page", action: "Open the product", verdict: "go", reason: "Clear listed price, no hidden extras on the page.", tip: "Note the listed price; checkout should match it." },
  { page: "Cart", action: "Click 'Go to checkout'", verdict: "stop", trick: "Protection plan add-on", reason: "A paid protection plan is ticked that the shopper never asked for.", tip: "Untick add-ons you were not asked to buy." },
  { page: "Checkout", action: "Click 'Continue to payment'", verdict: "stop", trick: "Surprise final fee", reason: "A new fee appears at the last step and the total jumps.", tip: "Compare the total with the cart before paying." },
  { page: "Payment page", action: "Click 'Pay now'", verdict: "go", reason: "Add-on removed, total matches the cart.", tip: "Pay only when the total matches what you saw." },
];

const STEP_MS = 1100;

export function Coach() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px 0px -20% 0px" });
  const reduced = usePrefersReducedMotion();
  const [shown, setShown] = useState(reduced ? STEPS.length : 0);
  const [run, setRun] = useState(0);

  useEffect(() => {
    if (reduced) { setShown(STEPS.length); return; }
    if (!inView) return;
    setShown(0);
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      setShown(i);
      if (i >= STEPS.length) window.clearInterval(id);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [inView, run, reduced]);

  const done = shown >= STEPS.length;
  return (
    <div className="wrap">
      <section className="section coach" aria-labelledby="coach-title">
        <Sign n="06" id="coach-title">Coach</Sign>
        <div className="coach-head">
          <h2 className="coach-h">Not just a gate: a coach.</h2>
          <span className="coach-proto">Prototype · illustration on a practice store</span>
        </div>
        <p className="coach-sub">PayCheck checks every page as the agent shops, and tells it why.</p>
        <div ref={ref} className="coach-body">
          <ol className="coach-steps" aria-live="polite">
            {STEPS.map((s, i) =>
              i < shown ? (
                <motion.li
                  key={`${run}-${i}`}
                  className={`coach-step is-${s.verdict}`}
                  initial={reduced ? false : { opacity: 0, x: -16 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                >
                  <span className="coach-node" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
                  <div className="coach-card">
                    <p className="coach-page">
                      <span className="coach-page-name">{s.page}</span>
                      <span className="coach-action">Agent's next action: {s.action}</span>
                    </p>
                    <p className="coach-verdict">
                      <span className={`coach-chip is-${s.verdict}`}>{s.verdict === "go" ? "Go" : "Stop"}</span>
                      {s.trick ? <span className="coach-trick">{s.trick}</span> : null}
                      <span className="coach-reason">{s.reason}</span>
                    </p>
                    <p className="coach-tip"><span>Tip for the agent:</span> {s.tip}</p>
                  </div>
                </motion.li>
              ) : null,
            )}
          </ol>
          <button type="button" className="coach-replay" onClick={() => setRun((r) => r + 1)} disabled={!done && !reduced}>
            Replay
          </button>
        </div>
      </section>
    </div>
  );
}
