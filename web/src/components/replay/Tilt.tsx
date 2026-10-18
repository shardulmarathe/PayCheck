import { useEffect, useRef } from "react";
import type { CSSProperties, ReactNode } from "react";

/**
 * 2.5D tilt: the panel leans slightly toward the cursor (max ±`max` deg) with perspective; children marked
 * with data-depth="n" sit n px forward (layered parallax, see .tilt [data-depth] in tokens.css).
 * Off for touch / coarse pointers and prefers-reduced-motion. Writes CSS vars only (no React re-render).
 */
export function Tilt({ children, className = "", max = 4, style }: { children: ReactNode; className?: string; max?: number; style?: CSSProperties }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el || !window.matchMedia) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || !window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
    let raf = 0;
    let tx = 0;
    let ty = 0;
    let cx = 0;
    let cy = 0;
    const step = () => {
      cx += (tx - cx) * 0.12;
      cy += (ty - cy) * 0.12;
      el.style.setProperty("--tilt-x", `${(-cy * max).toFixed(3)}deg`);
      el.style.setProperty("--tilt-y", `${(cx * max).toFixed(3)}deg`);
      el.style.setProperty("--glare-x", `${50 + cx * 40}%`);
      el.style.setProperty("--glare-y", `${50 + cy * 40}%`);
      if (Math.abs(tx - cx) > 0.001 || Math.abs(ty - cy) > 0.001) raf = requestAnimationFrame(step);
      else raf = 0;
    };
    const kick = () => {
      if (!raf) raf = requestAnimationFrame(step);
    };
    const move = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      tx = Math.max(-1, Math.min(1, ((e.clientX - r.left) / r.width) * 2 - 1));
      ty = Math.max(-1, Math.min(1, ((e.clientY - r.top) / r.height) * 2 - 1));
      el.classList.add("is-tilting");
      kick();
    };
    const leave = () => {
      tx = 0;
      ty = 0;
      el.classList.remove("is-tilting");
      kick();
    };
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => {
      el.removeEventListener("pointermove", move);
      el.removeEventListener("pointerleave", leave);
      cancelAnimationFrame(raf);
    };
  }, [max]);
  return (
    <div ref={ref} className={`tilt ${className}`} style={style}>
      {children}
    </div>
  );
}
