import { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "./useReplay";

export type CutPhase = "idle" | "cover" | "reveal";

/** Shutter cut. Content swaps at 350 ms; the overlay finishes at 700 ms. */
export function useCut<T extends string>(key: T): { shown: T; phase: CutPhase } {
  const reduced = usePrefersReducedMotion();
  const [shown, setShown] = useState(key);
  const [phase, setPhase] = useState<CutPhase>("idle");
  const shownRef = useRef(key);

  useEffect(() => {
    if (key === shownRef.current) return;
    if (reduced) {
      shownRef.current = key;
      setShown(key);
      setPhase("idle");
      return;
    }
    setPhase("cover");
    const swap = window.setTimeout(() => {
      shownRef.current = key;
      setShown(key);
      setPhase("reveal");
    }, 350);
    const done = window.setTimeout(() => setPhase("idle"), 700);
    return () => {
      window.clearTimeout(swap);
      window.clearTimeout(done);
    };
  }, [key, reduced]);

  return { shown, phase };
}
