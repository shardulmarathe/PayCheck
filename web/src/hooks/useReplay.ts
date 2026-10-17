import { useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

function reducedNow(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function usePrefersReducedMotion(): boolean {
  const framer = useReducedMotion();
  const [mq, setMq] = useState(reducedNow);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = () => setMq(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return framer === true || mq;
}

/** Shared replay clock. Plays once when `active` becomes true. Clicking play restarts at the end. */
export function useReplay(duration: number, active: boolean) {
  const reduced = usePrefersReducedMotion();
  const [t, setT] = useState(() => (reducedNow() ? duration : 0));
  const [playing, setPlaying] = useState(false);
  const tRef = useRef(t);
  const started = useRef(false);

  useEffect(() => {
    if (reduced) {
      tRef.current = duration;
      setT(duration);
      setPlaying(false);
      return;
    }
    if (active && !started.current) {
      started.current = true;
      tRef.current = 0;
      setT(0);
      setPlaying(true);
    }
  }, [active, reduced, duration]);

  useEffect(() => {
    if (!playing || reduced) return;
    let frame = 0;
    let last = performance.now();
    const loop = (now: number) => {
      const next = Math.min(duration, tRef.current + (now - last));
      last = now;
      tRef.current = next;
      setT(next);
      if (next >= duration) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [playing, reduced, duration]);

  const seek = (ms: number) => {
    const next = Math.min(duration, Math.max(0, ms));
    tRef.current = next;
    setT(next);
  };

  const pause = () => setPlaying(false);

  const toggle = () => {
    if (reduced) return;
    if (tRef.current >= duration - 20) {
      tRef.current = 0;
      setT(0);
      setPlaying(true);
      return;
    }
    setPlaying((on) => !on);
  };

  return { t, playing, reduced, seek, pause, toggle };
}
