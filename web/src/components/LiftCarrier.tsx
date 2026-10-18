import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { replayLiftProgress } from "../lib/kioskLift";

/** A copy of the kiosk's trick line travels into the guarded replay panel. */
export function LiftCarrier({ label }: { label: string }) {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const card = ref.current;
    if (reduced) {
      document.querySelectorAll<HTMLElement>("[data-lift-panel]").forEach((panel) => {
        panel.style.opacity = "1";
      });
      return;
    }
    if (!card) return;
    let frame = 0;
    const place = () => {
      frame = 0;
      const from = document.querySelector("[data-trick-line]")?.getBoundingClientRect();
      const to = document.querySelector("[data-lift-target]")?.getBoundingClientRect();
      if (!from || !to) return;
      const t = replayLiftProgress();
      const p = Math.min(1, Math.max(0, (t - 0.06) / 0.82));
      const show = t > 0.06 && t < 0.9;
      const x = from.left + (to.left - from.left) * p;
      const y = from.top + (to.top - from.top) * p;
      const w = Math.max(180, from.width + (to.width - from.width) * p);
      card.style.opacity = show ? "1" : "0";
      card.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      card.style.width = `${w}px`;
      document.querySelectorAll<HTMLElement>("[data-lift-panel]").forEach((panel) => {
        const fade = Math.min(1, Math.max(0, (t - 0.62) / 0.28));
        panel.style.opacity = String(fade);
      });
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(place);
    };
    place();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
      document.querySelectorAll<HTMLElement>("[data-lift-panel]").forEach((panel) => {
        panel.style.opacity = "1";
      });
    };
  }, [reduced]);

  if (reduced) return null;
  return (
    <div ref={ref} className="lift-card" aria-hidden="true">
      <p>{label}</p>
    </div>
  );
}
