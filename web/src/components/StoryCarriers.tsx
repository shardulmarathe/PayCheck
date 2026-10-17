import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { mixHex } from "../lib/ease";

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

/** 0 while `from` is below the read line, 1 once `to` reaches it. */
function bridge(from: DOMRect, to: DOMRect): number {
  const gap = to.top - from.top;
  if (gap < 24) return from.top < window.innerHeight * 0.4 ? 1 : 0;
  return clamp01((window.innerHeight * 0.42 - from.top) / gap);
}

export function StoryCarriers() {
  const score = useRef<HTMLParagraphElement>(null);
  const ring = useRef<HTMLDivElement>(null);
  const dot = useRef<HTMLDivElement>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (reduced) return;
    let frame = 0;
    const faded = new Set<HTMLElement>();

    const fade = (node: HTMLElement | null, opacity: string) => {
      if (!node) return;
      node.style.opacity = opacity;
      faded.add(node);
    };

    const place = () => {
      frame = 0;
      const scoreEl = score.current;
      const from = document.querySelector<HTMLElement>("[data-guarded-total]");
      const red = document.querySelector<HTMLElement>("[data-unguarded-total]");
      const to = document.querySelector<HTMLElement>("[data-catch-slot]");
      if (scoreEl && from && to) {
        const a = from.getBoundingClientRect();
        const b = to.getBoundingClientRect();
        const p = bridge(a, b);
        const live = p > 0.04 && p < 0.96;
        const x = a.left + (b.left - a.left) * p;
        const y = a.top + (b.top - a.top) * p;
        scoreEl.style.opacity = live ? "1" : "0";
        scoreEl.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        scoreEl.textContent = p < 0.72 ? from.textContent : (to.textContent ?? "");
        fade(from, p < 0.08 ? "1" : String(1 - clamp01((p - 0.08) / 0.25)));
        fade(to, p > 0.9 ? "1" : String(clamp01((p - 0.7) / 0.2)));
        fade(red, String(1 - clamp01(p * 1.6)));
      }

      const ringEl = ring.current;
      const dotFrom = document.querySelector("[data-guard-dot]")?.getBoundingClientRect();
      const loop = document.querySelector("[data-loop-ring]")?.getBoundingClientRect();
      if (ringEl && dotFrom && loop) {
        const p = bridge(dotFrom, loop);
        const live = p > 0.04 && p < 0.97;
        const w = dotFrom.width + (loop.width - dotFrom.width) * p;
        const h = dotFrom.height + (loop.height - dotFrom.height) * p;
        const x = dotFrom.left + (loop.left - dotFrom.left) * p;
        const y = dotFrom.top + (loop.top - dotFrom.top) * p;
        ringEl.style.opacity = live ? "1" : "0";
        ringEl.style.width = `${Math.max(8, w)}px`;
        ringEl.style.height = `${Math.max(8, h)}px`;
        ringEl.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        ringEl.style.borderColor = mixHex("#EEF1F5", "#323A45", p);
      }

      const dotEl = dot.current;
      const miss = document.querySelector("[data-loop-last]")?.getBoundingClientRect();
      const future = document.querySelector("[data-future-first]")?.getBoundingClientRect();
      if (dotEl && miss && future) {
        const p = bridge(miss, future);
        const live = p > 0.02 && p < 0.98;
        const x = miss.left + (future.left - miss.left) * p;
        const y = miss.top + (future.top - miss.top) * p;
        dotEl.style.opacity = live ? "1" : "0";
        dotEl.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      }
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
      faded.forEach((node) => {
        node.style.opacity = "";
      });
    };
  }, [reduced]);

  if (reduced) return null;
  return (
    <>
      <p ref={score} className="story-score" aria-hidden="true" />
      <div ref={ring} className="story-ring" aria-hidden="true" />
      <div ref={dot} className="story-dot" aria-hidden="true" />
    </>
  );
}
