import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";

export interface TrickItem {
  /** The trick as it reads on the checkout page. */
  text: ReactNode;
  /** Stamp text, e.g. "Blocked · subscription trap". */
  label: string;
  /** Show a pre-ticked checkbox in front of the item. */
  box?: boolean;
}

/**
 * The catch, as a looping sequence: the shopper's cursor heads for a checkout item, PayCheck scans it,
 * red brackets snap shut, a red X and a strikethrough draw over it, and the BLOCKED stamp slams in.
 * Decorative (aria-hidden): it is not a result, a control, or part of the recorded data.
 * Loops only while on screen; reduced motion shows the caught state, still.
 */
export function TrickCatch({ items, size = "l" }: { items: TrickItem[]; size?: "l" | "m" }) {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const [run, setRun] = useState(false);
  const [index, setIndex] = useState(0);
  const item = items[index % items.length];

  useEffect(() => {
    const node = ref.current;
    if (!node || reduced) return;
    const observer = new IntersectionObserver(([entry]) => setRun(!!entry?.isIntersecting && entry.intersectionRatio >= 0.35), {
      threshold: [0, 0.35, 0.7],
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [reduced]);

  return (
    <div
      ref={ref}
      className={`tc tc-${size}`}
      data-run={run && !reduced ? "1" : "0"}
      data-still={reduced ? "1" : "0"}
      aria-hidden="true"
      onAnimationIteration={(event) => {
        if (event.target === event.currentTarget && items.length > 1) setIndex((i) => (i + 1) % items.length);
      }}
    >
      <div className="tc-card">
        <span className="tc-scan" />
        <div className="tc-item">
          {item.box ? (
            <span className="tc-box">
              <svg viewBox="0 0 12 12">
                <path d="M2.5 6.2l2.4 2.3L9.6 3.6" />
              </svg>
            </span>
          ) : null}
          <span className="tc-text">
            {item.text}
            <span className="tc-strike" />
          </span>
          <span className="tc-brackets">
            <i />
            <i />
            <i />
            <i />
          </span>
          <svg className="tc-x">
            {/* Percentage coordinates (no viewBox stretch) keep the stroke uniform and the 0..1 dash draw-on exact. */}
            <line x1="4%" y1="8%" x2="96%" y2="92%" pathLength="1" />
            <line x1="96%" y1="8%" x2="4%" y2="92%" pathLength="1" />
          </svg>
        </div>
        <p className="tc-stamp">{item.label}</p>
      </div>
      <svg className="tc-cursor" viewBox="0 0 24 24" width="28" height="28">
        <path d="M3 2 L20 12 L12.5 13.6 L9 21 Z" />
      </svg>
    </div>
  );
}

/** Back-compat wrapper for the single subscription example. */
export function HiddenTrick({ label, children }: { id?: string; kind?: "solid" | "dashed"; label: string; children: ReactNode }) {
  return <TrickCatch items={[{ text: children, label, box: true }]} />;
}
