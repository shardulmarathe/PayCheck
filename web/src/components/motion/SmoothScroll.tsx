import Lenis from "lenis";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useIntroPhase } from "./Intro";

const LenisContext = createContext<Lenis | null>(null);

export function useLenis(): Lenis | null {
  return useContext(LenisContext);
}

/** One scroll engine. Lenis drives window scroll; Framer useScroll reads that same position. */
export function SmoothScroll({ children }: { children: ReactNode }) {
  const phase = useIntroPhase();
  const [lenis, setLenis] = useState<Lenis | null>(null);

  useEffect(() => {
    // Reduced motion: native scrolling, no smoothing.
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const instance = new Lenis({
      lerp: 0.085,
      smoothWheel: true,
      syncTouch: false,
      autoRaf: false,
    });
    let frame = 0;
    const loop = (time: number) => {
      instance.raf(time);
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    setLenis(instance);
    return () => {
      cancelAnimationFrame(frame);
      instance.destroy();
      setLenis(null);
    };
  }, []);

  useEffect(() => {
    if (!lenis) return;
    if (phase === "done") lenis.start();
    else lenis.stop();
  }, [lenis, phase]);

  return <LenisContext.Provider value={lenis}>{children}</LenisContext.Provider>;
}
