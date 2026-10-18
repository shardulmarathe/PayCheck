import { useEffect, useState } from "react";
import type { Tone } from "./replayRuns";
import "./shield.css";

/**
 * Payment intercepted by a shield.
 * A card chip flies from the agent toward the merchant's Pay endpoint.
 *  - no guard: it reaches Pay (red when the run paid for a trick, neutral when it was an honest buy)
 *  - PayCheck block: a neon shield materialises mid-flight, the chip hits it, shatters and deflects
 *  - PayCheck pass: the shield scans the chip and lets it through to Pay in green
 * Fully driven by `t` (ms) so a frozen frame renders deterministically.
 */

export type TokenState = { kind: "hold" | "block" | "pay"; tone?: Tone; at: number; fromP: number } | null;

const TRACK_L = 11; // % where the chip starts
const TRACK_R = 86; // % where Pay sits
const GATE = 50; // % where the shield sits
const FLY_TO_GATE = 800;
const FLY_ON = 700;

const clamp = (x: number) => Math.min(1, Math.max(0, x));
const easeOut = (x: number) => 1 - (1 - clamp(x)) ** 3;
const easeIn = (x: number) => clamp(x) ** 2;
const lerp = (a: number, b: number, k: number) => a + (b - a) * k;

export interface ShieldInterceptProps {
  token: TokenState;
  /** ms on the same clock as token.at; Infinity renders the settled end state */
  t: number;
  guarded: boolean;
  amount: string;
  animate?: boolean;
  /** time the guard verdict landed (for block: when the hold started) */
  holdAt?: number;
}

export function ShieldIntercept({ token, t, guarded, amount, animate = true, holdAt }: ShieldInterceptProps) {
  const now = animate ? t : Number.POSITIVE_INFINITY;
  const kind = token?.kind ?? null;
  const dt = token ? now - token.at : 0;
  const gateEdge = GATE - 5.5;
  const START = TRACK_L + 13;

  // chip position (% of width), lift and visibility
  let x = START;
  let y = 0;
  let rot = 0;
  let chipOpacity = token ? 1 : 0;
  let chipTone: "neutral" | "red" | "green" | "check" = "neutral";
  if (kind === "hold") {
    x = lerp(START, gateEdge, easeOut(dt / FLY_TO_GATE));
    y = dt > FLY_TO_GATE ? Math.sin((dt - FLY_TO_GATE) / 160) * 2 : 0;
    chipTone = "check";
  } else if (kind === "block") {
    const k = clamp(dt / 650);
    x = gateEdge - 9 * easeOut(k);
    y = 34 * easeIn(k);
    rot = -38 * easeOut(k);
    chipOpacity = 1 - clamp((dt - 250) / 400);
    chipTone = "red";
  } else if (kind === "pay") {
    const from = token && token.fromP > 0 ? gateEdge : START;
    x = lerp(from, TRACK_R - 7.5, easeOut(dt / (token && token.fromP > 0 ? FLY_ON : FLY_ON + 300)));
    chipTone = token?.tone === "red" ? "red" : token?.tone === "green" ? "green" : "neutral";
  }
  const arrived = kind === "pay" && dt > (token && token.fromP > 0 ? FLY_ON : FLY_ON + 300) - 60;

  // shield
  const shieldOn = guarded && (kind === "hold" || kind === "block" || (kind === "pay" && token?.tone === "green"));
  const shieldSince = kind === "hold" ? dt - 200 : 9999;
  const shieldScale = !shieldOn ? 0 : kind === "hold" ? easeOut(shieldSince / 380) : 1;
  const shieldState = kind === "block" ? "is-block" : kind === "pay" ? "is-pass" : "is-scan";
  const impact = kind === "block" ? clamp(dt / 700) : 0;
  const passFlash = kind === "pay" && guarded ? 1 - clamp(dt / 600) : 0;
  void holdAt;

  const fillTo = kind === "block" ? gateEdge : x;
  const lineTone = kind === "block" ? "red" : chipTone === "check" ? "green" : chipTone;

  return (
    <div className={`si${guarded ? " is-guarded" : ""}`} aria-hidden="true">
      <div className="si-node si-agent">
        <AgentGlyph />
        <span>agent</span>
      </div>
      <div className="si-track" />
      <div className={`si-fill tone-${lineTone}`} style={{ left: `${TRACK_L}%`, width: `${Math.max(0, fillTo - TRACK_L)}%` }} />

      {guarded && (
        <div
          className={`si-shield ${shieldState}`}
          style={{ left: `${GATE}%`, transform: `translate(-50%, -50%) scale(${shieldScale})`, opacity: shieldOn ? 1 : 0.0 }}
        >
          <svg viewBox="0 0 64 72">
            <path d="M32 3 6 12v20c0 17 11 30 26 37 15-7 26-20 26-37V12z" fill="currentColor" fillOpacity=".1" stroke="currentColor" strokeWidth="2.5" />
            <path d="M32 12 14 18v14c0 11 7 20 18 25 11-5 18-14 18-25V18z" fill="none" stroke="currentColor" strokeOpacity=".45" strokeWidth="1.2" strokeDasharray="3 3" />
            {kind === "block" ? (
              <g stroke="currentColor" strokeWidth="4" strokeLinecap="round">
                <path d="M24 26 40 42" strokeDasharray="23" strokeDashoffset={23 * (1 - clamp(dt / 220))} />
                <path d="M40 26 24 42" strokeDasharray="23" strokeDashoffset={23 * (1 - clamp((dt - 150) / 220))} />
              </g>
            ) : kind === "pay" ? (
              <path d="m22 34 7 7 14-15" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
            ) : (
              <rect x="14" y={18 + ((Math.max(0, shieldSince) / 9) % 38)} width="36" height="2" fill="currentColor" opacity=".9" />
            )}
          </svg>
          {kind === "hold" && <span className="si-ring" style={{ animationDelay: "0s" }} />}
          {impact > 0 && impact < 1 && <span className="si-flash" style={{ opacity: 1 - impact, transform: `translate(-50%, -50%) scale(${1 + impact * 1.6})` }} />}
          {passFlash > 0 && <span className="si-flash is-green" style={{ opacity: passFlash, transform: `translate(-50%, -50%) scale(${1 + (1 - passFlash) * 1.4})` }} />}
        </div>
      )}

      {kind === "block" &&
        SHARDS.map((s, i) => {
          const k = easeOut(dt / 750);
          const a = (s.a * Math.PI) / 180;
          return (
            <i
              key={i}
              className="si-shard"
              style={{
                left: `${gateEdge}%`,
                transform: `translate(${Math.cos(a) * s.d * k}px, ${Math.sin(a) * s.d * k + 18 * k * k}px) rotate(${s.r * k}deg)`,
                opacity: 1 - clamp((dt - 300) / 450),
                width: s.w,
                height: s.w * 0.6,
              }}
            />
          );
        })}

      {token && (
        <div className={`si-chip tone-${chipTone}`} style={{ left: `min(${x}%, calc(97.5% - var(--si-pay-room)))`, transform: `translate(-100%, calc(-50% + ${y}px)) rotate(${rot}deg)`, opacity: chipOpacity }}>
          <span className="si-chip-gold" />
          <span className="si-chip-num">•••• 4242</span>
        </div>
      )}

      <div className={`si-node si-pay${arrived ? ` is-hit tone-${chipTone}` : ""}${kind === "block" ? " is-safe" : ""}`}>
        <span className="si-pay-amt">Pay {amount}</span>
        <span className="si-pay-sub">{kind === "block" ? "no payment" : arrived ? (chipTone === "red" ? "paid" : "paid ✓") : "merchant"}</span>
      </div>
    </div>
  );
}

const SHARDS = [
  { a: 200, d: 58, r: -160, w: 10 },
  { a: 160, d: 64, r: 120, w: 8 },
  { a: 235, d: 46, r: 200, w: 7 },
  { a: 130, d: 40, r: -90, w: 9 },
  { a: 260, d: 34, r: 140, w: 6 },
  { a: 185, d: 80, r: -220, w: 6 },
  { a: 110, d: 52, r: 260, w: 7 },
  { a: 215, d: 92, r: 90, w: 5 },
];

const AgentGlyph = () => (
  <svg viewBox="0 0 20 20">
    <rect x="3" y="5" width="14" height="10" rx="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="7.5" cy="10" r="1.3" fill="currentColor" />
    <circle cx="12.5" cy="10" r="1.3" fill="currentColor" />
    <path d="M10 2v3" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

/** Standalone, self-playing version: mode "unguarded" (paid the trick), "block" or "pass". Loops. */
export function ShieldInterceptDemo({ mode, amount = "$12.49", frozenAt, loopMs = 4200 }: { mode: "unguarded" | "block" | "pass"; amount?: string; frozenAt?: number; loopMs?: number }) {
  const [t, setT] = useState(frozenAt ?? 0);
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  useEffect(() => {
    if (frozenAt !== undefined || reduced) return;
    let raf = 0;
    const start = performance.now();
    const tick = (n: number) => {
      setT((n - start) % loopMs);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [frozenAt, reduced, loopMs]);
  const tt = reduced ? Number.POSITIVE_INFINITY : t;
  let token: TokenState = null;
  if (mode === "unguarded") token = tt >= 200 ? { kind: "pay", tone: "red", at: 200, fromP: 0 } : null;
  else if (mode === "block") token = tt >= 1600 ? { kind: "block", at: 1600, fromP: 0.5 } : tt >= 200 ? { kind: "hold", at: 200, fromP: 0 } : null;
  else token = tt >= 1600 ? { kind: "pay", tone: "green", at: 1600, fromP: 0.5 } : tt >= 200 ? { kind: "hold", at: 200, fromP: 0 } : null;
  if (reduced) token = mode === "unguarded" ? { kind: "pay", tone: "red", at: 0, fromP: 0 } : mode === "block" ? { kind: "block", at: 0, fromP: 0.5 } : { kind: "pay", tone: "green", at: 0, fromP: 0.5 };
  return <ShieldIntercept token={token} t={tt} guarded={mode !== "unguarded"} amount={amount} animate={!reduced} />;
}
