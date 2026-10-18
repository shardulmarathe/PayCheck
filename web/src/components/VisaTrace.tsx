import { useInView } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { SITE } from "../lib/copy";
import { Sign, Tag } from "./Sign";
import type { VisaScene, VisaTrace as VisaTraceData } from "../lib/types";

/**
 * Renders structured, whitelisted fields only (see loader/runData.ts parseVisa).
 * Signal red marks a stop (rejected request or the guard's trick block); green marks a step that went through.
 * There is no generic JSON/pre dump here, so raw request fields can't print even if a trace carries them.
 * Every word on the diagram comes from the trace itself or from the field labels this section already used.
 */
function checkLine(scene: VisaScene): string {
  const status = scene.check.status != null ? ` · HTTP ${scene.check.status}` : "";
  return `${scene.check.accepted ? "accept" : "reject"}${status}`;
}

type HopState = "ok" | "stop" | "skip";

interface Hop {
  key: string;
  label: string;
  value: string;
  notes: string[];
  state: HopState;
}

function hopsFor(scene: VisaScene): Hop[] {
  const rejected = !scene.check.accepted;
  const blocked = scene.guard?.verdict === "block";
  const checkNote = scene.check.reason ?? (scene.check.accepted ? "signature accepted" : "");
  return [
    { key: "agent", label: "Agent", value: "", notes: [], state: "ok" },
    {
      key: "check",
      label: "Signed agent check",
      value: checkLine(scene),
      notes: checkNote ? [checkNote] : [],
      state: rejected ? "stop" : "ok",
    },
    {
      key: "guard",
      label: "Guard verdict",
      value: scene.guard ? (blocked ? "Block" : "Allow") : rejected ? "not reached" : "not called",
      notes: scene.guard
        ? [scene.guard.trick ? `trick: ${scene.guard.trick}` : "", scene.guard.evidence ? `evidence: ${scene.guard.evidence}` : ""].filter(Boolean)
        : [],
      state: !scene.guard ? "skip" : blocked ? "stop" : "ok",
    },
    { key: "pay", label: "Payment", value: scene.paid ? "paid (mock)" : "not made (mock)", notes: [], state: scene.paid ? "ok" : "skip" },
  ];
}

/** Index of the last hop the request actually reached (it stops at the first stop/skip). */
function lastReached(hops: Hop[]): number {
  let last = 0;
  for (let i = 1; i < hops.length; i += 1) {
    if (hops[i].state === "skip") break;
    last = i;
    if (hops[i].state === "stop") break;
  }
  return last;
}

const LIT_MS = 520;
const TRAVEL_MS = 560;
const HOLD_MS = 2600;

function Scene({ scene }: { scene: VisaScene }) {
  const rejected = !scene.check.accepted;
  const blocked = scene.guard?.verdict === "block";
  return (
    <li>
      <h3>{scene.title}</h3>
      <dl>
        <dt>Signed agent check</dt>
        <dd>
          {checkLine(scene)} {scene.check.reason ?? (scene.check.accepted ? "signature accepted" : "")}
        </dd>
        <dt>Guard verdict</dt>
        <dd>
          {scene.guard ? (
            <>
              {blocked ? "Block" : "Allow"}
              {scene.guard.trick ? ` · trick: ${scene.guard.trick}` : ""}
              {scene.guard.evidence ? ` · evidence: ${scene.guard.evidence}` : ""}
            </>
          ) : rejected ? (
            "not reached"
          ) : (
            "not called"
          )}
        </dd>
        <dt>Payment</dt>
        <dd>{scene.paid ? "paid (mock)" : "not made (mock)"}</dd>
      </dl>
    </li>
  );
}

function TraceFlow({ trace }: { trace: VisaTraceData }) {
  const reduced = usePrefersReducedMotion();
  const root = useRef<HTMLDivElement>(null);
  const inView = useInView(root, { once: true, margin: "0px 0px -20% 0px" });
  const scenes = trace.scenes;
  const settleOn = Math.max(
    0,
    scenes.findIndex((s) => s.guard?.verdict === "block"),
  );
  const [index, setIndex] = useState(reduced ? settleOn : 0);
  const [auto, setAuto] = useState(!reduced);
  const [replay, setReplay] = useState(0);
  const scene = scenes[index];
  const hops = useMemo(() => hopsFor(scene), [scene]);
  const reach = lastReached(hops);
  const doneAt = 2 * reach + 2; // 1 = agent lit, 2k = travel into hop k, 2k+1 = hop k lit, doneAt = stamp
  const [progress, setProgress] = useState(reduced ? 99 : 0);
  const playing = inView && !reduced;

  // Step the packet through the hops of the current scene.
  useEffect(() => {
    if (reduced) {
      setProgress(99);
      return;
    }
    if (!inView) return;
    setProgress(0);
    let step = 0;
    let timer = 0;
    const next = () => {
      step += 1;
      setProgress(step);
      if (step >= doneAt) return;
      timer = window.setTimeout(next, step % 2 === 0 ? TRAVEL_MS : LIT_MS);
    };
    timer = window.setTimeout(next, 260);
    return () => window.clearTimeout(timer);
  }, [index, replay, inView, reduced, doneAt]);

  // Auto-advance once through every scene, then rest on the guard's block.
  useEffect(() => {
    if (!auto || !playing || progress < doneAt) return;
    const timer = window.setTimeout(() => {
      if (index + 1 < scenes.length) setIndex(index + 1);
      else {
        setAuto(false);
        setIndex(settleOn);
      }
    }, HOLD_MS);
    return () => window.clearTimeout(timer);
  }, [auto, playing, progress, doneAt, index, scenes.length, settleOn]);

  const done = progress >= doneAt;
  const stopHop = hops.find((hop, i) => i <= reach && hop.state === "stop");
  const stamp = stopHop ? stopHop.value : hops[reach].value;
  const hopState = (i: number): string => {
    const lit = i === 0 ? progress >= 1 : progress >= 2 * i + 1;
    if (i <= reach) return lit ? hops[i].state : "idle";
    return done ? "skip" : "idle";
  };
  const segState = (i: number): string => {
    // segment i joins hop i and hop i+1
    if (i + 1 > reach) return done ? "off" : "idle";
    if (progress === 2 * (i + 1)) return "travel";
    if (progress > 2 * (i + 1)) return hops[i + 1].state === "stop" ? "stop" : "ok";
    return "idle";
  };

  const lines: { text: string; state: string; at: number }[] = [
    { text: `> ${scene.title}`, state: "head", at: 1 },
    ...hops.slice(1).map((hop, k) => {
      const i = k + 1;
      const pad = hop.label.toLowerCase().padEnd(19, " ");
      const text = `${pad}${hop.value}${hop.notes.length ? `  ${hop.notes.join("  ")}` : ""}`;
      return { text, state: i <= reach ? hop.state : "skip", at: i <= reach ? 2 * i + 1 : doneAt };
    }),
  ];

  return (
    <div ref={root} className="tap" data-done={done ? "1" : "0"} data-kind={stopHop ? "stop" : "ok"}>
      <div className="tap-scenes" role="tablist" aria-label="Recorded scenes">
        {scenes.map((s, i) => (
          <button
            key={s.title}
            type="button"
            role="tab"
            aria-selected={i === index}
            className={i === index ? "tap-chip is-on" : "tap-chip"}
            onClick={() => {
              setAuto(false);
              if (i === index) setReplay((r) => r + 1);
              else setIndex(i);
            }}
          >
            <span className={!s.check.accepted || s.guard?.verdict === "block" ? "tap-dot stop" : "tap-dot ok"} aria-hidden="true" />
            {s.title}
          </button>
        ))}
      </div>

      <div className="tap-flow" aria-hidden="true">
        {hops.map((hop, i) => (
          <div key={hop.key} className="tap-cell">
            <div className="tap-hop" data-state={hopState(i)}>
              <span className="tap-node">
                <i />
                <i />
                <i />
                <i />
              </span>
              <span className="tap-label">{hop.label}</span>
              {hop.value ? <span className="tap-value">{hop.value}</span> : null}
              {hop.notes.map((note) => (
                <span key={note} className="tap-note">
                  {note}
                </span>
              ))}
            </div>
            {i < hops.length - 1 ? (
              <span className="tap-seg" data-state={segState(i)}>
                <b />
              </span>
            ) : null}
          </div>
        ))}
      </div>

      <div className="tap-term" aria-hidden="true">
        <div className="tap-term-bar">
          <b>Checkpoint log</b>
          <em>{`${index + 1}/${scenes.length}`}</em>
        </div>
        <ol className="tap-lines">
          {lines.map((line) => (
            <li key={line.text} data-state={line.state} data-on={progress >= line.at ? "1" : "0"} style={{ ["--n" as string]: line.text.length }}>
              <code>{line.text}</code>
            </li>
          ))}
        </ol>
        <Tag verdict={stopHop ? "held" : "cleared"} className={done ? "tap-stamp is-on" : "tap-stamp"} detail={`${stopHop ? "✕ " : "✓ "}${stamp}`} />
      </div>
      <p className="sr-only" aria-live="polite">
        {done ? `${scene.title}. ${hops.slice(1).map((h) => `${h.label}: ${h.value}${h.notes.length ? `, ${h.notes.join(", ")}` : ""}`).join(". ")}.` : ""}
      </p>
    </div>
  );
}

export function VisaSection({ traces }: { traces: VisaTraceData[] }) {
  if (traces.length === 0) return null;
  return (
    <div className="wrap">
      <section className="section" aria-labelledby="visa-title">
        <Sign n="05" as="p">
          {SITE.visaKicker}
        </Sign>
        <h2 id="visa-title" className="h1 cp-title">
          {traces[0].heading}
        </h2>
        {traces.map((trace) => (
          <div key={trace.id}>
            <TraceFlow trace={trace} />
            <ol className="sr-only">
              {trace.scenes.map((scene) => (
                <Scene key={scene.title} scene={scene} />
              ))}
            </ol>
          </div>
        ))}
      </section>
    </div>
  );
}
