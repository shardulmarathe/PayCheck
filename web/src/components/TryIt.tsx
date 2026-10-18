import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { DEMO_PAGES, SITE, TRY_IT_URL } from "../lib/copy";
import { liveCheck } from "../lib/liveCheck";
import type { LiveCheck } from "../lib/liveCheck";
import { Bracket, Stamp, usePrefersReducedMotion } from "./replay/ReplayStage";
import { Tilt } from "./replay/Tilt";
import "./replay/replay.css";
import "./tryit/tryit.css";
import { TRY_PAGES } from "./tryit/tryitRecorded";
import type { TryPage } from "./tryit/types";

/*
 * Try it: eight demo store pages. Clicking a page plays PayCheck's check. Prefers a live /api/check
 * answer when the warm window is open; otherwise uses the recorded response for that page.
 */

const T = { sent: 350, scan: 600, scanDur: 1500, verdict: 2150, bracket: 2450, stamp: 2900, instr: 3350, label: 3900, end: 4300 } as const;
const EASE = [0.2, 0.8, 0.2, 1] as const;

const PAGES: TryPage[] = DEMO_PAGES.map((d) => TRY_PAGES.find((p) => p.title === d.title)).filter((p): p is TryPage => Boolean(p));

type ActiveResponse = {
  verdict: "block" | "pass";
  trick: string;
  evidence: string;
  instruction: string;
  live: boolean;
  latency_ms?: number;
};

function useRunClock(runKey: number, reduced: boolean) {
  const [t, setT] = useState(reduced ? Infinity : 0);
  useEffect(() => {
    if (reduced) {
      setT(Infinity);
      return;
    }
    let raf = 0;
    const start = performance.now();
    setT(0);
    const tick = (now: number) => {
      const el = now - start;
      setT(el);
      if (el < T.end + 200) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [runKey, reduced]);
  return t;
}

function recordedOf(page: TryPage): ActiveResponse {
  return {
    verdict: page.response.verdict === "block" ? "block" : "pass",
    trick: page.response.trick,
    evidence: page.response.evidence,
    instruction: page.response.instruction,
    live: false,
  };
}

function fromLive(live: LiveCheck): ActiveResponse {
  return {
    verdict: live.verdict,
    trick: live.attack_type ?? "none",
    evidence: live.evidence ?? "",
    instruction: live.instruction ?? "",
    live: true,
    latency_ms: live.latency_ms,
  };
}

export function TryIt() {
  const reduced = usePrefersReducedMotion();
  const animate = !reduced;
  const [sel, setSel] = useState(0);
  const [runKey, setRunKey] = useState(0);
  const [checked, setChecked] = useState<Set<number>>(() => new Set());
  /** Per-tile resolved answer for the latest run on that tile. */
  const [answers, setAnswers] = useState<Record<number, ActiveResponse>>({});
  /** Current run's answer; undefined while liveCheck is in flight past start. */
  const [current, setCurrent] = useState<ActiveResponse | null>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const t = useRunClock(runKey, reduced);
  const page = PAGES[sel];

  const run = useCallback(
    (i: number) => {
      setSel(i);
      setRunKey((k) => k + 1);
      setChecked((prev) => new Set(prev).add(i));
      setCurrent(null);
      const el = stageRef.current;
      if (el && window.matchMedia("(max-width: 900px)").matches) {
        const r = el.getBoundingClientRect();
        if (r.top < 0 || r.top > window.innerHeight * 0.6) el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
      }
    },
    [reduced],
  );

  // Fire liveCheck in parallel with the animation. Fall back to recorded once the scan finishes
  // if the call has not resolved (helper's own 10s timeout must not freeze the UI).
  useEffect(() => {
    if (runKey === 0) return;
    const target = PAGES[sel];
    if (!target) return;
    const ctrl = new AbortController();
    let settled = false;
    const apply = (ans: ActiveResponse) => {
      if (settled) return;
      settled = true;
      setCurrent(ans);
      setAnswers((prev) => ({ ...prev, [sel]: ans }));
    };
    liveCheck(target.id, { signal: ctrl.signal }).then((live) => {
      if (ctrl.signal.aborted) return;
      apply(live ? fromLive(live) : recordedOf(target));
    });
    const fallbackAt = window.setTimeout(() => {
      apply(recordedOf(target));
    }, T.scan + T.scanDur);
    return () => {
      settled = true;
      ctrl.abort();
      window.clearTimeout(fallbackAt);
    };
  }, [runKey, sel]);

  if (!page) return null;
  // While liveCheck is in flight, animate against the recorded response so timing never stalls.
  const active = current ?? recordedOf(page);
  const block = active.verdict === "block";
  const at = (ms: number) => t >= ms;
  const scanning = animate && t >= T.scan && t < T.scan + T.scanDur;
  const scanP = Math.min(1, Math.max(0, (t - T.scan) / T.scanDur));
  const started = checked.has(sel);
  const showLiveBadge = started && active.live && at(T.verdict);

  return (
    <div className="wrap">
      <section className="section" aria-labelledby="try-title">
        <p className="label">{SITE.tryKicker}</p>
        <h2 id="try-title" className="h1">
          {SITE.tryTitle}
        </h2>
        <p className="body-l">{SITE.tryBody}</p>

        <div className="tx">
          <div className="tx-pick" role="group" aria-label="Practice store pages">
            {PAGES.map((p, i) => {
              const ans = answers[i] ?? recordedOf(p);
              const isBlock = ans.verdict === "block";
              const done = checked.has(i);
              return (
                <button
                  key={p.id}
                  className={`tx-tile${i === sel ? " is-on" : ""}${done ? (isBlock ? " is-block" : " is-pass") : ""}`}
                  aria-pressed={i === sel}
                  aria-label={`${p.title}: run PayCheck on this page`}
                  onClick={() => run(i)}
                >
                  <span className="tx-n">{String(i + 1).padStart(2, "0")}</span>
                  <span className="tx-title">{p.title}</span>
                  <span className={`tx-v${done ? (isBlock ? " is-block" : " is-pass") : ""}`}>{done ? (isBlock ? "Block" : "Pass") : "check ▸"}</span>
                </button>
              );
            })}
          </div>

          <Tilt max={3}>
            <div className="tilt-inner tx-stage" ref={stageRef}>
              <div className="tx-stage-head">
                <span className="tx-lane">Lane B · PayCheck</span>
                <span className="tx-head-right">
                  {showLiveBadge ? (
                    <span className="tx-live" title={active.latency_ms != null ? `${active.latency_ms} ms` : undefined}>
                      LIVE{active.latency_ms != null ? ` · ${active.latency_ms} ms` : ""}
                    </span>
                  ) : null}
                  <span className="tx-verdict-meta">{!started ? "01 Ready" : !at(T.verdict) ? "02 Scanning" : block ? "03 Held" : "03 Cleared"}</span>
                </span>
              </div>

              <div className="rs-browser" data-depth="1">
                <div className="rs-urlbar">
                  <span className="rs-lights" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span className={`rs-url${page.kind === "payment" ? " is-suspect" : ""}`}>
                    <b>{page.domain}</b>
                    <span>{page.url.replace(/^https?:\/\/[^/]+/, "")}</span>
                  </span>
                </div>
                <div className="rs-viewport tx-viewport" style={{ ["--accent" as string]: accentFor(page.store) }}>
                  <AnimatePresence mode="popLayout" initial={false}>
                    <motion.div
                      key={page.id}
                      className="rs-page"
                      initial={animate ? { opacity: 0, x: 40 } : false}
                      animate={{ opacity: 1, x: 0 }}
                      exit={animate ? { opacity: 0, x: -40 } : { opacity: 0 }}
                      transition={{ duration: animate ? 0.42 : 0, ease: EASE }}
                    >
                      <TryStorePage page={page} response={active} brackets={started && block && at(T.bracket)} animate={animate} />
                    </motion.div>
                  </AnimatePresence>
                  {scanning && started && <div className="rs-scan" aria-hidden="true" style={{ top: `${scanP * 100}%` }} />}
                  <AnimatePresence>
                    {started && at(T.stamp) && (
                      <Stamp
                        key={`${page.id}-${runKey}-${active.live ? "live" : "rec"}`}
                        text={block ? "Block" : "Pass"}
                        reason={page.title}
                        tone={block ? "red" : "green"}
                        animate={animate}
                      />
                    )}
                  </AnimatePresence>
                  {!started && (
                    <button className="tx-run" onClick={() => run(sel)}>
                      <span aria-hidden="true">▸</span> Run PayCheck on this page
                    </button>
                  )}
                </div>
              </div>

              {started && at(T.end) && (
                <button className="tx-again" onClick={() => run(sel)}>
                  ↻ Run again
                </button>
              )}
            </div>
          </Tilt>
        </div>

        {TRY_IT_URL ? (
          <a className="try-button" href={TRY_IT_URL}>
            {SITE.tryButton}
          </a>
        ) : null}
      </section>
    </div>
  );
}

function accentFor(store: string): string {
  const m: Record<string, string> = { Voltmart: "#ffd36b", Soundnest: "#9fb6ff", Beanbarn: "#e8b35a", Greenleaf: "#d8c49a" };
  if (store.startsWith("Chargehub")) return "#b49cff";
  return m[store] ?? "#7aa8ff";
}

function TryStorePage({
  page,
  response,
  brackets,
  animate,
}: {
  page: TryPage;
  response: ActiveResponse;
  brackets: boolean;
  animate: boolean;
}) {
  const ev = response.evidence;
  const mark = (text: string, node: ReactNode, opts: { block?: boolean } = {}) =>
    ev && text === ev ? (
      <Bracket on={brackets} animate={animate} dashed pointer block={opts.block}>
        {node}
      </Bracket>
    ) : (
      node
    );
  const evInChecks = page.checks.some((c) => c.label === ev);

  const header = (
    <div className="st-head">
      <span className="st-logo">
        <span className="st-logo-mark" aria-hidden="true" />
        {page.store}
      </span>
      {page.kind !== "payment" && (
        <span className="st-nav" aria-hidden="true">
          <span>Shop</span>
          <span>Deals</span>
        </span>
      )}
    </div>
  );

  if (page.verify) {
    const v = page.verify;
    return (
      <div className="st st-verify">
        {header}
        <div className="st-card">
          <span className="st-badge">{v.badge}</span>
          <h4 className="st-h">{v.heading}</h4>
          {mark(v.body, <p className="st-evidence">{v.body}</p>, { block: true })}
          <div className="st-fields">
            {v.fields.map((f) => (
              <label key={f} className="st-field">
                <span>{f}</span>
                <span className="st-input" />
              </label>
            ))}
          </div>
          <div className="st-actions">
            <span className="st-btn">{page.button}</span>
            <span className="st-link">Cancel</span>
          </div>
        </div>
      </div>
    );
  }

  const before = page.notes.filter((n) => n.where === "before");
  const after = page.notes.filter((n) => n.where === "after");
  return (
    <div className="st">
      {header}
      <div className="st-card">
        <h4 className="st-h">{page.heading}</h4>
        {page.items.map((it) => (
          <div className="st-row" key={it.label}>
            <span className="st-row-l">{evInChecks ? it.label : mark(it.label, <span>{it.label}</span>)}</span>
            <span className="st-row-r">{mark(it.amount, <span>{it.amount}</span>)}</span>
          </div>
        ))}
        {before.map((n) => (
          <p className="st-note" key={n.text}>
            {mark(n.text, <span>{n.text}</span>)}
          </p>
        ))}
        <div className="st-total">
          <span>Order total</span>
          <b>{page.total}</b>
        </div>
        {brackets && page.was && page.items.some((it) => it.amount === ev) && (
          <motion.p className="st-listed-tx" initial={animate ? { opacity: 0, y: 6 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: animate ? 0.4 : 0 }}>
            listed {page.was} · checkout {ev}
          </motion.p>
        )}
        {after.map((n) => (
          <p className="st-note is-fine" key={n.text}>
            {mark(n.text, <span>{n.text}</span>)}
          </p>
        ))}
        {page.checks.map((c) => (
          <div className="st-check" key={c.label}>
            <span className={`st-box${c.checked ? " is-checked" : ""}`} aria-hidden="true">
              {c.checked ? "✓" : ""}
            </span>
            <span className="st-check-l">{mark(c.label, <span>{c.label}</span>)}</span>
            {c.amount && <span className="st-row-r">{c.amount}</span>}
          </div>
        ))}
        <p className="st-saved">
          <span className="st-chip" aria-hidden="true">
            •••• 4242
          </span>
          Pay with saved card ending 4242.
        </p>
        <div className="st-actions">
          <span className="st-btn">{page.button}</span>
          <span className="st-link">Leave without paying</span>
        </div>
      </div>
    </div>
  );
}
