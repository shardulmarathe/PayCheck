import type { MotionValue } from "framer-motion";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { LOOP } from "../lib/copy";
import { useDriver } from "./motion/Pin";

/**
 * How PayCheck was built, as one cycle (high level): train the guard -> Browser Use agents test it ->
 * the attacker builds new tricks -> mistakes go back into training -> repeat. A page token runs the lane once per pass,
 * a counter counts passes 1..6 (a count only: no meter, no rising bars, nothing implying a pass beat the last), and the
 * line holds on the caption "...shipped round 4". Replaces the round-14 linear Pipeline; the intake/outro facts moved here.
 * Scroll drives it when pinned; on phones it loops on its own clock. Reduced motion: no token, final state.
 */
const PASSES = LOOP.passes;
const SPAN = 0.86; // passes play over 0..SPAN, the rest holds on the caption
const PASS_MS = 4200;
const clamp = (v: number, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const pad = (n: number) => String(n).padStart(2, "0");

/** Clockwise around a square lane, starting at the top middle (station 01). viewBox units 0..100. */
const L = 14;
const R = 86;
function lanePoint(f: number): [number, number] {
  let d = (((f % 1) + 1) % 1) * (R - L) * 4;
  const segs: [number, number, number, number][] = [
    [50, L, R, L],
    [R, L, R, R],
    [R, R, L, R],
    [L, R, L, L],
    [L, L, 50, L],
  ];
  for (const [x0, y0, x1, y1] of segs) {
    const len = Math.abs(x1 - x0) + Math.abs(y1 - y0);
    if (d <= len) {
      const k = len ? d / len : 0;
      return [x0 + (x1 - x0) * k, y0 + (y1 - y0) * k];
    }
    d -= len;
  }
  return [50, L];
}
const LANE_PATH = `M50 ${L} H${R} V${R} H${L} V${L} H50`;
const STATION_AT = [0, 0.25, 0.5, 0.75].map(lanePoint);
const CHEVRONS = [0.06, 0.125, 0.19, 0.31, 0.375, 0.44, 0.56, 0.625, 0.69, 0.81, 0.875, 0.94];
const TRAIL = [0.035, 0.07, 0.105];

export function TrainingLoop({ progress }: { progress: MotionValue<number> | null }) {
  const reduced = usePrefersReducedMotion();
  const [t, ref] = useDriver(progress, (PASS_MS * PASSES) / SPAN, 1);
  const hold = reduced || t >= SPAN;
  const run = clamp(t / SPAN) * PASSES;
  const pass = hold ? PASSES : Math.min(PASSES, Math.floor(run) + 1);
  const phase = hold ? 0 : run - Math.floor(run);
  const station = hold ? -1 : Math.min(3, Math.floor(clamp(phase + 0.06) * 4));
  // What the token carries on each leg: a trained guard, then shopper runs, then a new trick page, then a mistake going back.
  const leg = Math.floor(clamp(phase) * 4);
  const [tx, ty] = lanePoint(phase);

  return (
    <div ref={ref} className="tl" data-hold={hold ? "1" : "0"}>
      <Column items={LOOP.intake} className="tl-in" />

      <figure className="tl-loop" aria-label={`Training loop: ${LOOP.stations.map((s) => s.title).join(", then ")}, then repeat. ${LOOP.caption}`}>
        <svg className="tl-lane" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path d={LANE_PATH} className="tl-lane-bed" vectorEffect="non-scaling-stroke" />
          <path d={LANE_PATH} className={reduced ? "tl-lane-ants is-still" : "tl-lane-ants"} vectorEffect="non-scaling-stroke" />
          {!hold ? <path d={LANE_PATH} className="tl-lane-trace" pathLength={1} strokeDasharray={`${phase} 1`} vectorEffect="non-scaling-stroke" /> : null}
        </svg>
        {CHEVRONS.map((f) => {
          const [x, y] = lanePoint(f);
          const dir = f < 0.25 ? 45 : f < 0.5 ? 135 : f < 0.75 ? 225 : 315;
          return <i key={f} className="tl-chev" aria-hidden="true" style={{ left: `${x}%`, top: `${y}%`, transform: `translate(-50%,-50%) rotate(${dir}deg)` }} />;
        })}

        <div className="tl-core" aria-hidden="true">
          <span className="tl-core-k">Pass</span>
          <span className="tl-core-n" key={pass}>
            {pad(pass)}
            <small> / {pad(PASSES)}</small>
          </span>
          {hold ? (
            <span className="cp-tag is-cleared tl-ship">
              <span className="cp-tag-body">
                <span className="cp-tag-hole" />
                <span className="cp-tag-label">Round {LOOP.shipped}</span>
                <span className="cp-tag-verdict">SHIPPED</span>
              </span>
            </span>
          ) : (
            <span className="tl-core-t">{station >= 0 ? LOOP.stations[station].short : ""}</span>
          )}
        </div>

        {LOOP.stations.map((s, i) => {
          const [x, y] = STATION_AT[i];
          const state = hold ? "done" : i === station ? "on" : "off";
          const local = clamp((phase - i * 0.25 + 0.06) / 0.25);
          return (
            <div key={s.k} className={`tl-st tl-st-${i}`} data-state={state} style={{ left: `${x}%`, top: `${y}%` }} data-scan>
              <span className="tl-st-head">
                <em>Station {s.k}</em>
                <b>{state === "on" ? "Active" : hold ? "Cleared" : "Standby"}</b>
              </span>
              <p className="tl-st-t">
                <span className="tl-st-long">{s.title}</span>
                <span className="tl-st-short">{s.short}</span>
              </p>
              <p className="tl-st-b">{s.body}</p>
              <StationViz viz={s.viz} on={state === "on"} local={local} still={reduced} />
            </div>
          );
        })}

        {!hold
          ? TRAIL.map((lag, k) => {
              const [x, y] = lanePoint(phase - lag);
              return phase - lag > 0 ? <span key={lag} className="tl-ghost" style={{ left: `${x}%`, top: `${y}%`, opacity: 0.5 - k * 0.14 }} aria-hidden="true" /> : null;
            })
          : null}
        {!hold ? (
          <span className={`tl-page leg-${leg}`} style={{ left: `${tx}%`, top: `${ty}%` }} aria-hidden="true">
            <i />
            <i />
            <i />
            {leg === 2 ? <b>Miss</b> : null}
          </span>
        ) : null}
      </figure>

      <div className="tl-out">
        <p className="tl-caption" data-hold={hold ? "1" : "0"}>
          {LOOP.caption}
        </p>
        <div className="tl-io tl-catch">
          <span className="tl-io-k">{LOOP.catches.k}</span>
          <p className="tl-io-t">{LOOP.catches.title}</p>
          <ul className="tl-catch-list">
            {LOOP.catches.items.map((it) => (
              <li key={it}>{it}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function Column({ items, className }: { items: { k: string; title: string; body: string }[]; className?: string }) {
  return (
    <ul className={className ? `tl-io-list ${className}` : "tl-io-list"}>
      {items.map((it) => (
        <li key={it.title} className="tl-io">
          <span className="tl-io-k">{it.k}</span>
          <p className="tl-io-t">{it.title}</p>
          <p className="tl-io-b">{it.body}</p>
        </li>
      ))}
    </ul>
  );
}

/** Small per-station animation. Decorative only: no numbers. */
function StationViz({ viz, on, local, still }: { viz: string; on: boolean; local: number; still: boolean }) {
  const k = on && !still ? local : 1;
  if (viz === "train")
    return (
      <span className="tl-viz tl-viz-train" aria-hidden="true">
        <span className="tl-viz-steps">
          <span style={{ transform: `scaleX(${k})` }} />
        </span>
        {on && !still ? <span className="tl-xray" style={{ left: `${local * 100}%` }} /> : null}
        <span className="tl-viz-read">veri.studio</span>
      </span>
    );
  if (viz === "shop")
    return (
      <span className="tl-viz tl-viz-lanes" aria-hidden="true">
        {["With", "Without"].map((lane, n) => (
          <span key={lane} className="tl-viz-lane">
            <em>{lane}</em>
            <span className="tl-viz-track">
              {[0, 1, 2].map((d) => {
                const x = on && !still ? ((local * 1.6 + d / 3) % 1) * 100 : 18 + d * 26;
                const stop = n === 0 && x > 70;
                return <i key={d} className={stop ? "held" : n === 1 && x > 70 ? "lost" : undefined} style={{ left: `${stop ? 70 : x}%` }} />;
              })}
              {n === 0 ? <b className="tl-viz-gate" /> : null}
            </span>
          </span>
        ))}
      </span>
    );
  if (viz === "attack")
    return (
      <span className="tl-viz tl-viz-pages" aria-hidden="true">
        {[0, 1, 2, 3, 4, 5].map((n) => (
          <i key={n} className={n % 2 ? "twin" : "trick"} style={{ ["--k" as string]: n, opacity: on && !still ? clamp(local * 6 - n) : 1 }} />
        ))}
      </span>
    );
  return (
    <span className="tl-viz tl-viz-miss" aria-hidden="true">
      <span className="tl-viz-misstag" style={{ transform: `translateX(${on && !still ? local * 18 : 0}px)` }}>
        MISS
      </span>
      <span className="tl-viz-read">Right / wrong</span>
    </span>
  );
}
