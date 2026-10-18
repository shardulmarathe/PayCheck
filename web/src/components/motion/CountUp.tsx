import { animate, useInView } from "framer-motion";
import { useEffect, useRef } from "react";
import { usePrefersReducedMotion } from "../../hooks/useReplay";

export function CountUp({
  to,
  decimals = 0,
  start = true,
  duration = 0.9,
  className,
}: {
  to: number;
  decimals?: number;
  start?: boolean;
  duration?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true, margin: "0px" });
  const reduced = usePrefersReducedMotion();
  const done = useRef(false);
  const final = to.toFixed(decimals);

  useEffect(() => {
    const node = ref.current;
    if (!node || done.current) return;
    if (reduced) {
      node.textContent = final;
      done.current = true;
      return;
    }
    if (!inView || !start) return;
    done.current = true;
    // Terminal feel: a block caret rides the number while it ticks, then a short glow when it lands.
    node.dataset.tick = "1";
    const controls = animate(0, to, {
      duration,
      ease: [0.2, 0.8, 0.2, 1],
      onUpdate: (value) => {
        node.textContent = value.toFixed(decimals);
      },
      onComplete: () => {
        node.textContent = final;
        node.dataset.tick = "done";
      },
    });
    return () => controls.stop();
  }, [inView, start, reduced, to, decimals, duration, final]);

  return (
    <span
      ref={ref}
      className={className ? `count-up ${className}` : "count-up"}
      style={decimals === 0 ? { minWidth: `${final.length}ch` } : undefined}
      aria-label={final}
    >
      {reduced ? final : (0).toFixed(decimals)}
    </span>
  );
}

/** "34 of 52" → counts the leading number; the rest of the text stays put. */
export function CountUpText({ text, start = true }: { text: string; start?: boolean }) {
  const match = /^(\d+)(.*)$/.exec(text);
  if (!match) return <>{text}</>;
  return (
    <>
      <CountUp to={Number(match[1])} start={start} />
      {match[2]}
    </>
  );
}
