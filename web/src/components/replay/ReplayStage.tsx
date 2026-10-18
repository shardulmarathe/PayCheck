import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import "./replay.css";
import { Tilt } from "./Tilt";
import { SAVED_CARD_LINE, SCENARIOS } from "./replayRuns";
import type { LogLine, PageKind, PaneEvent, PaneRun, Scenario, ScenarioId, Target, Tone } from "./replayRuns";

const HOLD_MS = 3600;
const TYPE_CPS = 90; // characters per second for the terminal lines
const EASE = [0.2, 0.8, 0.2, 1] as const;

export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false,
  );
  useEffect(() => {
    if (!window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setReduced(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return reduced;
}

/* ---------------------------------------------------------------- pane state at time t */

interface PaneState {
  page: PageKind;
  target: Target;
  clickAt: number | null;
  scanFrom: number | null;
  scanDur: number;
  verdict: "pass" | "block" | null;
  brackets: string[];
  stamp: PaneEvent["stamp"] | null;
  fill: number;
  outcome: PaneEvent["outcome"] | null;
  outcomeAt: number;
  doneMsg: string;
  logs: Array<{ line: LogLine; at: number }>;
  token: { kind: "hold" | "block" | "pay"; tone?: Tone; at: number; fromP: number } | null;
}

function stateAt(run: PaneRun, t: number): PaneState {
  const s: PaneState = {
    page: "product",
    target: null,
    clickAt: null,
    scanFrom: null,
    scanDur: 0,
    verdict: null,
    brackets: [],
    stamp: null,
    fill: 0,
    outcome: null,
    outcomeAt: 0,
    doneMsg: "",
    logs: [],
    token: null,
  };
  for (const ev of run.events) {
    if (ev.at > t) break;
    if (ev.page && ev.page !== s.page) {
      s.page = ev.page;
      s.scanFrom = null;
      s.brackets = [];
      s.fill = 0;
      s.clickAt = null;
    }
    if (ev.target !== undefined) s.target = ev.target;
    if (ev.click) s.clickAt = ev.at;
    if (ev.scan) {
      s.scanFrom = ev.at;
      s.scanDur = ev.scan;
      s.verdict = null;
    }
    if (ev.verdict) s.verdict = ev.verdict;
    if (ev.bracket) s.brackets = ev.bracket;
    if (ev.stamp) {
      s.stamp = ev.stamp;
    }
    if (ev.token) s.token = { ...ev.token, at: ev.at, fromP: s.token?.kind === "hold" ? 0.5 : 0 };
    if (ev.fill !== undefined) s.fill = ev.fill;
    if (ev.outcome) {
      s.outcome = ev.outcome;
      s.outcomeAt = ev.at;
    }
    if (ev.doneMsg) s.doneMsg = ev.doneMsg;
    if (ev.log) s.logs.push({ line: ev.log, at: ev.at });
  }
  return s;
}

/* ---------------------------------------------------------------- clock */

function useClock(end: number, opts: { frozenAt?: number; reduced: boolean; onLoop: () => void; resetKey: string }) {
  const { frozenAt, reduced, onLoop, resetKey } = opts;
  const [t, setT] = useState(frozenAt ?? (reduced ? end : 0));
  const [playing, setPlaying] = useState(frozenAt === undefined && !reduced);
  const base = useRef<number | null>(null);
  const offset = useRef(0);
  const loopRef = useRef(onLoop);
  loopRef.current = onLoop;

  useEffect(() => {
    offset.current = frozenAt ?? (reduced ? end : 0);
    base.current = null;
    setT(offset.current);
    setPlaying(frozenAt === undefined && !reduced);
  }, [resetKey, frozenAt, reduced, end]);

  useEffect(() => {
    if (!playing) return;
    let raf = 0;
    const tick = (now: number) => {
      if (base.current === null) base.current = now - offset.current;
      const next = now - base.current;
      if (next >= end + HOLD_MS) {
        base.current = null;
        offset.current = 0;
        setT(0);
        loopRef.current();
        return;
      }
      offset.current = next;
      setT(next);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, end, resetKey]);

  const toggle = useCallback(() => {
    base.current = null;
    if (offset.current >= end) offset.current = 0;
    setPlaying((p) => !p);
  }, [end]);
  const restart = useCallback(() => {
    base.current = null;
    offset.current = 0;
    setT(0);
    setPlaying(true);
  }, []);
  return { t, playing, toggle, restart };
}

/* ---------------------------------------------------------------- public component */


function shopperAsk(instruction: string): string {
  const body = instruction.replace(/\.$/, "");
  const lowered = body.charAt(0).toLowerCase() + body.slice(1);
  return `The shopper was asked to ${lowered}.`;
}

function inspectionMeta(sc: Scenario): { code: string; trick: string; detail: string; held: boolean } {
  if (sc.id === "price") {
    const listed = sc.product.price;
    return { code: "04", trick: "Price", detail: `Checkout price ${sc.total} · listed ${listed}`, held: true };
  }
  if (sc.id === "fake") {
    return { code: "05", trick: "Fake card", detail: "Fake verification page asking for card details", held: true };
  }
  return { code: "03", trick: "Honest", detail: `Order total ${sc.total} · no trick found`, held: false };
}

function formatResult(outcome: NonNullable<PaneEvent["outcome"]>, guarded: boolean): string {
  if (guarded && (outcome.head === "No order" || /nothing charged/i.test(outcome.sub))) {
    return "RESULT  Held · nothing charged";
  }
  if (outcome.tone === "red" && /^Paid\s/.test(outcome.head)) {
    const over = outcome.sub.match(/\$[\d.]+/);
    const paid = outcome.head.replace(/^Paid\s+/, "");
    return over ? `RESULT  Paid ${paid}  (+${over[0]} over listed)` : `RESULT  Paid ${paid}`;
  }
  if (outcome.tone === "red") {
    return `RESULT  ${outcome.head}`;
  }
  return `RESULT  ${outcome.head}`;
}

export interface ReplayStageProps {
  initialScenario?: ScenarioId;
  /** Freeze the clock at this ms offset (screenshots). */
  frozenAt?: number;
  /** Move to the next scenario after each replay ends. */
  autoAdvance?: boolean;
}

export function ReplayStage({ initialScenario = "price", frozenAt, autoAdvance = true }: ReplayStageProps) {
  const reduced = usePrefersReducedMotion();
  const [id, setId] = useState<ScenarioId>(initialScenario);
  const sc = useMemo(() => SCENARIOS.find((s) => s.id === id) ?? SCENARIOS[0], [id]);
  const advance = useCallback(() => {
    if (!autoAdvance) return;
    const i = SCENARIOS.findIndex((s) => s.id === id);
    setId(SCENARIOS[(i + 1) % SCENARIOS.length].id);
  }, [autoAdvance, id]);
  const { t, playing, toggle, restart } = useClock(sc.end, { frozenAt, reduced, onLoop: advance, resetKey: id });
  const animate = !reduced;
  const progress = Math.min(1, t / sc.end);

  const ask = shopperAsk(sc.instruction);

  return (
    <section className="rs" aria-label="PayCheck security checkpoint: no guard versus PayCheck">
      <header className="rs-top">
        <div className="rs-tabs" role="tablist" aria-label="Checkpoint scenarios">
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              role="tab"
              aria-selected={s.id === id}
              className={`rs-tab${s.id === id ? " is-on" : ""}${s.id === "tax" ? " is-honest" : ""}`}
              onClick={() => setId(s.id)}
            >
              {s.tab}
            </button>
          ))}
        </div>
      </header>

      <div className="rs-errand">
        <p className="rs-kicker">{sc.kicker}</p>
        <p className="rs-ask">{ask}</p>
      </div>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={sc.id}
          className="rs-panes"
          initial={animate ? { opacity: 0, y: 18 } : false}
          animate={{ opacity: 1, y: 0 }}
          exit={animate ? { opacity: 0, y: -12 } : { opacity: 0 }}
          transition={{ duration: animate ? 0.45 : 0, ease: EASE }}
        >
          <Tilt>
            <Pane sc={sc} run={sc.left} t={t} animate={animate} />
          </Tilt>
          <Tilt>
            <Pane sc={sc} run={sc.right} t={t} animate={animate} />
          </Tilt>
        </motion.div>
      </AnimatePresence>

      <footer className="rs-foot">
        <div className="rs-controls">
          <button className="rs-btn" onClick={toggle} aria-label={playing ? "Pause replay" : "Play replay"} disabled={frozenAt !== undefined}>
            {playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <button className="rs-btn" onClick={restart} aria-label="Restart replay" disabled={frozenAt !== undefined}>
            <RestartIcon />
          </button>
          <div className="rs-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(progress * 100)} aria-label="Replay progress">
            <div className="rs-progress-fill" style={{ transform: `scaleX(${progress})` }} />
          </div>
        </div>
      </footer>
    </section>
  );
}

/* ---------------------------------------------------------------- pane */

function Pane({ sc, run, t, animate }: { sc: Scenario; run: PaneRun; t: number; animate: boolean }) {
  const s = stateAt(run, t);
  const guarded = run.mode === "guarded";
  const sweepMs = 900;
  const scanning = s.scanFrom !== null && t < s.scanFrom + s.scanDur;
  const scanP =
    s.scanFrom !== null ? Math.min(1, Math.max(0, (t - s.scanFrom) / Math.min(sweepMs, s.scanDur || sweepMs))) : 0;
  const xrayOn = guarded && s.scanFrom !== null && t >= s.scanFrom && !s.outcome && (scanning || s.brackets.length > 0);
  const showContraband = xrayOn && s.brackets.length > 0;

  const domain = s.page === "verify" && sc.store.verifyDomain ? sc.store.verifyDomain : sc.store.domain;
  const path = pathFor(s.page, sc);
  const meta = inspectionMeta(sc);
  const verdictLabel =
    s.verdict === "block" ? "Held" : s.verdict === "pass" ? "Cleared" : scanning ? "Scanning" : "Pending";

  return (
    <article className={`tilt-inner rs-pane ${guarded ? "is-guarded" : "is-unguarded"}`}>
      <header className="rs-pane-head">
        <h3 className="rs-pane-title">{guarded ? "Lane B · PayCheck" : "Lane A · No guard"}</h3>
        <dl className="rs-meta">
          <div>
            <dt>01 SHOPPER</dt>
            <dd>{sc.product.name}</dd>
          </div>
          <div>
            <dt>02 STORE</dt>
            <dd>{sc.store.name}</dd>
          </div>
          <div>
            <dt>03 VERDICT</dt>
            <dd className={s.verdict === "block" ? "is-held" : undefined}>{guarded ? verdictLabel : "None"}</dd>
          </div>
        </dl>
      </header>

      <div className="rs-browser" data-depth="1">
        <div className="rs-urlbar">
          <span className="rs-lights" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className={`rs-url${s.page === "verify" ? " is-suspect" : ""}`}>
            <LockIcon />
            <b>{domain}</b>
            <span>{path}</span>
          </span>
        </div>

        <div className="rs-viewport" style={{ ["--accent" as string]: sc.store.accent, ["--scan" as string]: `${scanP * 100}%` }}>
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.div
              key={s.page}
              className="rs-page"
              style={xrayOn ? { clipPath: `inset(${(scanning ? scanP : 1) * 100}% 0 0 0)` } : undefined}
              initial={animate ? { opacity: 0, x: 24 } : false}
              animate={{ opacity: 1, x: 0 }}
              exit={animate ? { opacity: 0, x: -24 } : { opacity: 0 }}
              transition={{ duration: animate ? 0.38 : 0, ease: EASE }}
            >
              <StorePage sc={sc} s={s} t={t} animate={animate} guarded={guarded} />
            </motion.div>
          </AnimatePresence>

          {xrayOn && (
            <div className="rs-xray" aria-hidden="true">
              <div
                className="rs-xray-layer"
                style={{ clipPath: `inset(0 0 calc(100% - ${(scanning ? scanP : 1) * 100}%) 0)` }}
              >
                <div className="rs-page">
                  <StorePage sc={sc} s={s} t={t} animate={false} guarded={guarded} xray />
                </div>
              </div>
              {scanning && animate && <div className="rs-scan" style={{ top: `${scanP * 100}%` }} />}
            </div>
          )}
          {showContraband && (
            <div className="rs-contraband" aria-hidden="true">
              <div className="rs-page">
                <StorePage sc={sc} s={s} t={t} animate={animate} guarded={guarded} />
              </div>
            </div>
          )}

          <AnimatePresence>
            {s.stamp && (
              <InspectionTag
                key={s.stamp.text + s.page}
                code={meta.code}
                trick={meta.trick}
                detail={meta.detail}
                held={meta.held || s.stamp.tone === "red"}
                animate={animate}
              />
            )}
          </AnimatePresence>

          <AnimatePresence>
            {s.outcome && (
              <motion.div
                className={`rs-outcome tone-${s.outcome.tone === "red" ? "red" : "neutral"}`}
                initial={animate ? { y: "100%", opacity: 0 } : false}
                animate={{ y: 0, opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: animate ? 0.5 : 0, ease: EASE }}
              >
                <span className="rs-outcome-line">
                  <Typed text={formatResult(s.outcome, guarded)} from={s.outcomeAt} t={animate ? t : Infinity} />
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </article>
  );
}

function pathFor(page: PageKind, sc: Scenario): string {
  const slug = sc.product.name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  if (page === "product") return `/shop/${slug}`;
  if (page === "cart") return `/shop/${slug}/cart`;
  if (page === "checkout") return `/shop/${slug}/checkout`;
  if (page === "verify") return `/verify/${slug}`;
  return `/shop/${slug}/done`;
}

/* ---------------------------------------------------------------- store pages */

function StorePage({ sc, s, t, animate, guarded, xray = false }: { sc: Scenario; s: PaneState; t: number; animate: boolean; guarded: boolean; xray?: boolean }) {
  const pressed = (tgt: Target) => !xray && s.target === tgt && s.clickAt !== null && t - s.clickAt < 320;
  const agentOn = (tgt: Target) => !xray && s.target === tgt;
  const brackets = xray ? [] : s.brackets;

  const header = (
    <div className="st-head">
      <span className="st-logo">
        <span className="st-logo-mark" aria-hidden="true" />
        {s.page === "verify" ? `${sc.store.name} Secure Verify` : sc.store.name}
      </span>
      {s.page !== "verify" && (
        <span className="st-nav" aria-hidden="true">
          <span>Shop</span>
          <span>Deals</span>
          <span className="st-cart-ico">
            <CartIcon />
            {s.page !== "product" && <i>1</i>}
          </span>
        </span>
      )}
    </div>
  );

  if (s.page === "product") {
    return (
      <div className="st">
        {header}
        <div className="st-product">
          <div className="st-art">
            <ProductArt kind={sc.store.art} />
          </div>
          <div className="st-info">
            <p className="st-crumb">Shop / {sc.store.art === "coffee" ? "Coffee" : sc.store.art === "pens" ? "Stationery" : "Chargers"}</p>
            <h4 className="st-title">{sc.product.name}</h4>
            <p className="st-price">{sc.product.price}</p>
            <AgentButton on={agentOn("add")} pressed={pressed("add")} animate={animate}>
              Add to cart
            </AgentButton>
            <p className="st-fine">Free returns · Ships in 2 days</p>
          </div>
        </div>
      </div>
    );
  }

  if (s.page === "cart") {
    return (
      <div className="st">
        {header}
        <div className="st-card">
          <h4 className="st-h">Your cart</h4>
          {sc.cart.map((l) => (
            <Row key={l.label} label={l.label} amount={l.amount} thumb={sc.store.art} />
          ))}
          <div className="st-actions">
            <AgentButton on={agentOn("checkout")} pressed={pressed("checkout")} animate={animate}>
              Checkout
            </AgentButton>
          </div>
        </div>
      </div>
    );
  }

  if (s.page === "checkout") {
    return (
      <div className="st">
        {header}
        <div className="st-card">
          <h4 className="st-h">Review and pay</h4>
          {sc.checkout.map((l) => (
            <Row
              key={l.label}
              label={l.label}
              amount={
                l.id === "price" ? (
                  <Bracket on={brackets.includes("price")} animate={animate} dashed pointer>
                    {l.amount}
                  </Bracket>
                ) : (
                  l.amount
                )
              }
              thumb={l.label === "Sales tax" ? undefined : sc.store.art}
            />
          ))}
          <div className="st-total">
            <span>Order total</span>
            <b>{sc.total}</b>
          </div>
          {guarded && sc.listedNote && brackets.includes("price") && (
            <motion.p
              className="st-listed"
              initial={animate ? { opacity: 0, y: 6 } : false}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: animate ? 0.4 : 0, ease: EASE }}
            >
              {sc.listedNote}
            </motion.p>
          )}
          <p className="st-saved">
            <span className="st-chip" aria-hidden="true">
              •••• 4242
            </span>
            {SAVED_CARD_LINE}
          </p>
          <div className="st-actions">
            <AgentButton on={agentOn("place")} pressed={pressed("place")} animate={animate}>
              Place order
            </AgentButton>
            <span className="st-link">Leave without paying</span>
          </div>
        </div>
      </div>
    );
  }

  if (s.page === "verify" && sc.verify) {
    const v = sc.verify;
    return (
      <div className="st st-verify">
        {header}
        <div className="st-card">
          <Bracket on={brackets.includes("badge")} animate={animate} dashed>
            <span className="st-badge">{v.badge}</span>
          </Bracket>
          {brackets.includes("badge") && <span className="st-annot">fake badge on the attacker's page</span>}
          <h4 className="st-h">{v.heading}</h4>
          <Bracket on={brackets.includes("evidence")} animate={animate} dashed block pointer>
            <p className="st-evidence">{v.evidence}</p>
          </Bracket>
          <div className={`st-fields${agentOn("fields") ? " is-agent" : ""}`}>
            {v.fields.map((f, i) => (
              <label key={f} className="st-field">
                <span>{f}</span>
                <span className="st-input" aria-label={`${f}, masked`}>
                  {i < s.fill ? <MaskedDots n={f === "Expiry" ? 4 : f === "CVV" ? 3 : f === "Card number" ? 16 : 10} animate={animate} /> : null}
                </span>
              </label>
            ))}
          </div>
          <div className="st-actions">
            <AgentButton on={agentOn("verify")} pressed={pressed("verify")} animate={animate}>
              {v.button}
            </AgentButton>
            <span className="st-link">Cancel</span>
          </div>
        </div>
      </div>
    );
  }

  // done page: the store's confirmation text, verbatim from shop.py
  return (
    <div className="st">
      {header}
      <div className="st-card st-done">
        <span className={`st-done-ico tone-${guarded ? "green" : "neutral"}`} aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <path d="m5 12.5 4.5 4.5L19 7.5" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
        <h4 className="st-h">{s.doneMsg}</h4>
      </div>
    </div>
  );
}

function Row({ label, amount, thumb }: { label: string; amount: ReactNode; thumb?: "coffee" | "pens" | "charger" }) {
  return (
    <div className="st-row">
      <span className="st-row-l">
        {thumb ? (
          <span className="st-thumb">
            <ProductArt kind={thumb} />
          </span>
        ) : (
          <span className="st-thumb is-empty" />
        )}
        {label}
      </span>
      <span className="st-row-r">{amount}</span>
    </div>
  );
}

function AgentButton({ on, pressed, animate, children }: { on: boolean; pressed: boolean; animate: boolean; children: ReactNode }) {
  return (
    <span className="st-btn-wrap">
      <motion.span
        className={`st-btn${on ? " is-target" : ""}`}
        animate={{ scale: pressed && animate ? 0.94 : 1 }}
        transition={{ duration: 0.12 }}
      >
        {children}
      </motion.span>
      <AnimatePresence>
        {on && (
          <motion.span
            className="st-agent"
            initial={animate ? { opacity: 0, x: 28, y: 22 } : false}
            animate={{ opacity: 1, x: 0, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: animate ? 0.45 : 0, ease: EASE }}
            aria-hidden="true"
          >
            <PointerIcon />
            <span>agent</span>
          </motion.span>
        )}
      </AnimatePresence>
      {pressed && animate && <span className="st-ripple" aria-hidden="true" />}
    </span>
  );
}

export function Bracket({
  on,
  animate,
  dashed,
  block,
  pointer: _pointer,
  children,
}: {
  on: boolean;
  animate: boolean;
  dashed?: boolean;
  block?: boolean;
  pointer?: boolean;
  children: ReactNode;
}) {
  return (
    <span className={`rs-br${block ? " is-block" : ""}${on ? " is-on" : ""}${dashed ? " is-dashed" : ""}${on ? " is-contraband" : ""}`}>
      {children}
      <AnimatePresence>
        {on &&
          (["tl", "tr", "bl", "br"] as const).map((c, i) => (
            <motion.i
              key={c}
              className={`rs-corner c-${c}`}
              initial={animate ? { opacity: 0, scale: 2.2 } : false}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={animate ? { type: "spring", stiffness: 700, damping: 26, delay: i * 0.04 } : { duration: 0 }}
              aria-hidden="true"
            />
          ))}
      </AnimatePresence>
    </span>
  );
}

export function MaskedDots({ n, animate }: { n: number; animate: boolean }) {
  return (
    <span className="st-dots">
      {Array.from({ length: n }, (_, i) => (
        <motion.i
          key={i}
          initial={animate ? { opacity: 0, scale: 0.3 } : false}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: animate ? 0.12 : 0, delay: animate ? i * 0.02 : 0 }}
        />
      ))}
    </span>
  );
}

/* ---------------------------------------------------------------- stamp + pay rail */

export function InspectionTag({
  code,
  trick,
  detail,
  held,
  animate,
}: {
  code: string;
  trick: string;
  detail: string;
  held: boolean;
  animate: boolean;
}) {
  return (
    <motion.div
      className={`rs-tag${held ? " is-held" : " is-cleared"}`}
      initial={animate ? { opacity: 0, rotate: 10, y: -20, x: 10 } : false}
      animate={{ opacity: 1, rotate: 2, y: 0, x: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={animate ? { type: "spring", stiffness: 420, damping: 22 } : { duration: 0 }}
    >
      <svg className="rs-tag-string" viewBox="0 0 14 168" aria-hidden="true">
        <path d="M7 168 L7 4" fill="none" stroke="currentColor" strokeWidth="1.25" />
      </svg>
      <div className="rs-tag-body">
        <span className="rs-tag-hole" aria-hidden="true" />
        <span className="rs-tag-label">INSPECTION {code} · {trick}</span>
        <span className="rs-tag-verdict">{held ? "HELD" : "CLEARED"}</span>
        <span className="rs-tag-detail">{detail}</span>
      </div>
    </motion.div>
  );
}

/** @deprecated Prefer InspectionTag. Kept for TryIt until that section migrates. */
export function Stamp({ text, reason, tone, animate }: { text: string; reason: string; tone: Tone; animate: boolean }) {
  const held = tone === "red";
  return (
    <InspectionTag
      code={held ? "04" : "03"}
      trick={reason.toUpperCase().slice(0, 18) || (held ? "BLOCK" : "CLEAR")}
      detail={text}
      held={held}
      animate={animate}
    />
  );
}

export function Typed({ text, from, t }: { text: string; from: number; t: number }) {
  const n = Number.isFinite(t) ? Math.max(0, Math.floor(((t - from) / 1000) * TYPE_CPS)) : text.length;
  if (n >= text.length) return <>{text}</>;
  return (
    <>
      <span className="sr-only">{text}</span>
      <span aria-hidden="true">{text.slice(0, n)}</span>
    </>
  );
}

/* ---------------------------------------------------------------- icons + art */

function ProductArt({ kind }: { kind: "coffee" | "pens" | "charger" }) {
  if (kind === "coffee")
    return (
      <svg viewBox="0 0 120 120" aria-hidden="true">
        <defs>
          <linearGradient id="rs-bag" x1="0" x2="1">
            <stop offset="0" stopColor="#3a2a1d" />
            <stop offset="1" stopColor="#5a4028" />
          </linearGradient>
        </defs>
        <path d="M34 24h52l6 12v64a6 6 0 0 1-6 6H34a6 6 0 0 1-6-6V36z" fill="url(#rs-bag)" />
        <path d="M34 24h52l6 12H28z" fill="#6d4c2f" />
        <rect x="40" y="52" width="40" height="30" rx="4" fill="#e8b35a" />
        <ellipse cx="60" cy="67" rx="8" ry="11" fill="#3a2a1d" />
        <path d="M60 57c-3 6 3 14 0 20" stroke="#e8b35a" strokeWidth="2" fill="none" />
      </svg>
    );
  if (kind === "pens")
    return (
      <svg viewBox="0 0 120 120" aria-hidden="true">
        {["#7aa8ff", "#ff8fb1", "#c9d1db", "#ffd36b", "#b49cff"].map((c, i) => (
          <g key={c} transform={`translate(${30 + i * 13} 20) rotate(${-8 + i * 4} 6 40)`}>
            <rect width="10" height="70" rx="4" fill="#1c2430" />
            <rect y="0" width="10" height="18" rx="4" fill={c} />
            <path d="M2 70h6l-3 10z" fill={c} />
          </g>
        ))}
      </svg>
    );
  return (
    <svg viewBox="0 0 120 120" aria-hidden="true">
      <rect x="36" y="34" width="48" height="56" rx="12" fill="#e9ecf2" />
      <rect x="36" y="34" width="48" height="56" rx="12" fill="url(#rs-chg)" opacity=".25" />
      <rect x="50" y="20" width="6" height="16" rx="2" fill="#b9c0cc" />
      <rect x="64" y="20" width="6" height="16" rx="2" fill="#b9c0cc" />
      <rect x="53" y="70" width="14" height="6" rx="3" fill="#2a3140" />
      <text x="60" y="58" textAnchor="middle" fontSize="11" fontWeight="700" fill="#5b6475" fontFamily="sans-serif">
        20W
      </text>
      <defs>
        <linearGradient id="rs-chg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" />
          <stop offset="1" stopColor="#8a93a5" />
        </linearGradient>
      </defs>
    </svg>
  );
}

const LockIcon = () => (
  <svg className="rs-lock" viewBox="0 0 16 16" aria-hidden="true">
    <rect x="3.5" y="7" width="9" height="7" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.3" />
    <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" fill="none" stroke="currentColor" strokeWidth="1.3" />
  </svg>
);
const CartIcon = () => (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path d="M1.5 2h2l1.6 8h7.4l1.5-5.5H4.3" fill="none" stroke="currentColor" strokeWidth="1.3" />
    <circle cx="6" cy="13" r="1" fill="currentColor" />
    <circle cx="12" cy="13" r="1" fill="currentColor" />
  </svg>
);
const PointerIcon = () => (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3 1.5 13 8l-4.4 1.1L6.4 14z" fill="currentColor" stroke="#06080a" strokeWidth="1" />
  </svg>
);
const PlayIcon = () => (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path d="M4.5 3v10l8-5z" fill="currentColor" />
  </svg>
);
const PauseIcon = () => (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <rect x="4" y="3" width="3" height="10" fill="currentColor" />
    <rect x="9" y="3" width="3" height="10" fill="currentColor" />
  </svg>
);
const RestartIcon = () => (
  <svg viewBox="0 0 16 16" aria-hidden="true">
    <path d="M3 8a5 5 0 1 0 1.5-3.6" fill="none" stroke="currentColor" strokeWidth="1.5" />
    <path d="M3 2v3.5h3.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

export type { Tone };
