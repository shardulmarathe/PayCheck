import type { MotionValue } from "framer-motion";
import { useDriver } from "./motion/Pin";

/**
 * What's next, drawn: agent frameworks send payments through PayCheck running on your own device, then on to
 * banks and card networks. Each payment is checked; a trick is stopped. Labels come only from the What's next copy
 * (futureTitles, futureItems[2], futureDevice). Decorative (aria-hidden).
 */
const clamp = (v: number) => Math.min(1, Math.max(0, v));
const PACKETS = 6;

export function FutureVision({ progress }: { progress: MotionValue<number> | null }) {
  const [t, ref] = useDriver(progress, 8000, 1);
  // Scroll builds the picture (0 → 0.45); the flow then runs on its own clock.
  const build = progress ? clamp(t / 0.45) : 1;
  const show = (a: number) => clamp((build - a) / 0.2);
  return (
    <div ref={ref} className="fv" aria-hidden="true" style={{ ["--b" as string]: build.toFixed(3) }}>
      <span className="illus-tag fv-illus">Illustration</span>
      <div className="fv-col fv-left" style={{ opacity: show(0), transform: `translateX(${(1 - show(0)) * -30}px)` }}>
        <div className="fv-node">
          <em>03</em> Agent frameworks
        </div>
      </div>
      <div className="fv-link fv-l1">
        <span style={{ transform: `scaleX(${show(0.25)})` }} />
      </div>
      <div className="fv-device" style={{ opacity: show(0.15), transform: `scale(${0.9 + 0.1 * show(0.15)})` }}>
        <span className="fv-badge">Station 04 · Your device</span>
        <div className="fv-core">
          <span className="fv-ring" />
          <span className="fv-ring r2" />
          <b>PayCheck</b>
        </div>
      </div>
      <div className="fv-link fv-l2">
        <span style={{ transform: `scaleX(${show(0.45)})` }} />
      </div>
      <div className="fv-col fv-right" style={{ opacity: show(0.35), transform: `translateX(${(1 - show(0.35)) * 30}px)` }}>
        <div className="fv-node">
          <span className="fv-ico">▣</span>
          Banks
        </div>
        <div className="fv-node">
          <span className="fv-ico">◈</span>
          Card networks
        </div>
      </div>
      {build >= 1 ? (
        <div className="fv-flow">
          {Array.from({ length: PACKETS }, (_, i) => (
            <span key={i} className={i === 3 ? "fv-pkt is-trick" : "fv-pkt"} style={{ animationDelay: `${i * 0.62}s` }} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
