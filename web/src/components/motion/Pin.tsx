import { motion, motionValue, useMotionValueEvent, useScroll, useTransform, type MotionValue } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePrefersReducedMotion } from "../../hooks/useReplay";

/** A never-changing motion value so the hook order stays fixed when there is no pin. */
const fallbackMv = motionValue(0);

function wide(): boolean {
  return typeof window !== "undefined" && window.innerWidth > 800 && window.innerHeight > 560;
}

/**
 * A scroll-pinned stage. On desktop the block sticks for `vh` of scroll and hands its children a 0..1
 * progress for the pinned stretch; it glides in and out (fade + scale) around the pin, so there is no snap.
 * On phones and under reduced motion there is no pin: children get null and run on their own clock.
 */
export function Pin({ vh = 220, className, children }: { vh?: number; className?: string; children: (progress: MotionValue<number> | null) => ReactNode }) {
  const reduced = usePrefersReducedMotion();
  const [pinnable, setPinnable] = useState(wide);
  useEffect(() => {
    const onResize = () => setPinnable(wide());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  if (reduced || !pinnable) return <div className={className ? `pin-free ${className}` : "pin-free"}>{children(null)}</div>;
  return (
    <Pinned vh={vh} className={className}>
      {children}
    </Pinned>
  );
}

function Pinned({ vh, className, children }: { vh: number; className?: string; children: (progress: MotionValue<number>) => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  // Whole pass = vh + 100 (viewport). The pin holds from 100/(vh+100) to vh/(vh+100).
  const a = 100 / (vh + 100);
  const b = vh / (vh + 100);
  const inner = useTransform(scrollYProgress, (p) => Math.min(1, Math.max(0, (p - a) / (b - a))));
  const opacity = useTransform(scrollYProgress, [a - 0.14, a, b, b + 0.14], [0.15, 1, 1, 0.15]);
  const scale = useTransform(scrollYProgress, [a - 0.14, a, b, b + 0.14], [0.94, 1, 1, 0.96]);
  const y = useTransform(scrollYProgress, [a - 0.14, a, b, b + 0.14], [60, 0, 0, -40]);
  const [active, setActive] = useState(false);
  const body = useRef<HTMLDivElement>(null);
  useMotionValueEvent(scrollYProgress, "change", (p) => {
    setActive(p > a - 0.2 && p < b + 0.2);
    // Depth layers read --pp (-0.5..0.5 across the whole pass) for scroll-linked parallax.
    body.current?.parentElement?.style.setProperty("--pp", (p - 0.5).toFixed(4));
  });
  return (
    <div ref={ref} className={className ? `pin ${className}` : "pin"} style={{ height: `${vh}vh` }} data-active={active ? "1" : "0"}>
      <div className="pin-stick">
        <motion.div ref={body} className="pin-body" style={{ opacity, scale, y }}>
          {children(inner)}
        </motion.div>
      </div>
    </div>
  );
}

/**
 * Progress driver for a visual: follows the pin's scroll progress when there is one,
 * otherwise loops on its own clock while on screen. Reduced motion: holds at `still`.
 */
export function useDriver(progress: MotionValue<number> | null, loopMs: number, still = 1): [number, React.RefObject<HTMLDivElement | null>] {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [t, setT] = useState(() => (reduced ? still : progress ? progress.get() : 0));
  useMotionValueEvent(progress ?? (fallbackMv as MotionValue<number>), "change", (v) => {
    if (progress) setT(v);
  });
  useEffect(() => {
    if (reduced) {
      setT(still);
      return;
    }
    if (progress) {
      setT(progress.get());
      return;
    }
    const node = ref.current;
    if (!node) return;
    let frame = 0;
    let visible = false;
    let last = performance.now();
    let acc = 0;
    const loop = (now: number) => {
      const dt = now - last;
      last = now;
      if (visible) {
        acc = (acc + dt) % loopMs;
        setT(acc / loopMs);
      }
      frame = requestAnimationFrame(loop);
    };
    const io = new IntersectionObserver(([entry]) => {
      visible = !!entry?.isIntersecting;
    }, { threshold: 0.25 });
    io.observe(node);
    frame = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frame);
      io.disconnect();
    };
  }, [progress, reduced, loopMs, still]);
  return [t, ref];
}

