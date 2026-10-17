import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { easeInOutCubic, GLIDE, NAV_H } from "../../lib/motion";
import { PRODUCT_NAME } from "../../lib/product";
import { kioskPose, type KioskMode } from "../kioskPose";
import { usePrefersReducedMotion } from "../../hooks/useReplay";
import { sectionId, tabFromHash, type TabId } from "../../hooks/useRoute";
import { useLenis } from "./SmoothScroll";

interface NavValue {
  active: TabId;
  isGliding: boolean;
  arriving: TabId | null;
  glideTo: (id: TabId) => void;
}

const NavContext = createContext<NavValue>({
  active: "demo",
  isGliding: false,
  arriving: null,
  glideTo: () => {},
});

export function useNav(): NavValue {
  return useContext(NavContext);
}

function modeFor(tab: TabId): KioskMode {
  if (tab === "benchmarks" || tab === "future") return tab;
  if (tab === "design") return "design";
  return "demo";
}

export function NavProvider({ children }: { children: ReactNode }) {
  const lenis = useLenis();
  const reduced = usePrefersReducedMotion();
  const [active, setActive] = useState<TabId>(() => tabFromHash(window.location.hash));
  const [isGliding, setGliding] = useState(false);
  const [arriving, setArriving] = useState<TabId | null>(null);
  const glidingRef = useRef(false);
  glidingRef.current = isGliding;

  useEffect(() => {
    const nodes = [...document.querySelectorAll<HTMLElement>("[data-tab]")];
    const observer = new IntersectionObserver(
      (entries) => {
        if (glidingRef.current) return;
        const hit = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        const id = hit?.target.getAttribute("data-tab");
        if (id === "demo" || id === "benchmarks" || id === "browser" || id === "visa" || id === "design" || id === "future") setActive(id);
      },
      { rootMargin: "-40% 0px -55% 0px", threshold: [0, 0.25, 0.5, 1] },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!lenis) return;
    const id = tabFromHash(window.location.hash);
    if (id === "demo") return;
    const hash = sectionId(id);
    if (!document.getElementById(hash)) {
      window.history.replaceState(null, "", "#demo");
      setActive("demo");
      return;
    }
    const jump = () => lenis.scrollTo(`#${hash}`, { immediate: true, offset: -NAV_H, force: true });
    jump();
    const early = window.setTimeout(jump, 0);
    const late = window.setTimeout(jump, 60);
    return () => {
      window.clearTimeout(early);
      window.clearTimeout(late);
    };
  }, [lenis]);

  useEffect(() => {
    const tab = active === "demo" ? null : active;
    const label =
      tab === "benchmarks"
        ? "Benchmarks"
        : tab === "browser"
          ? "Browser Use"
          : tab === "visa"
            ? "Visa"
            : tab === "design"
              ? "Design process"
              : tab === "future"
                ? "Future improvements"
                : "";
    document.title = label ? `${PRODUCT_NAME} · ${label}` : PRODUCT_NAME;
  }, [active]);

  useEffect(() => {
    if (reduced) {
      kioskPose.mode = "demo";
      kioskPose.modeFrom = "demo";
      kioskPose.modeMix = 1;
      kioskPose.invalidate();
      return;
    }
    const next = modeFor(active);
    if (next === kioskPose.mode && kioskPose.modeMix >= 1) return;
    kioskPose.modeFrom = kioskPose.mode;
    kioskPose.mode = next;
    kioskPose.modeMix = 0;
    let start = 0;
    let frame = 0;
    const step = (now: number) => {
      if (!start) start = now;
      kioskPose.modeMix = Math.min(1, (now - start) / 250);
      kioskPose.invalidate();
      if (kioskPose.modeMix < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [active, reduced]);

  const glideTo = (id: TabId) => {
    const hash = sectionId(id);
    if (id !== "demo" && !document.getElementById(hash)) return;
    setActive(id);
    const writeHash = () => window.history.replaceState(null, "", `#${hash}`);
    if (!lenis || reduced) {
      writeHash();
      if (lenis) lenis.scrollTo(`#${hash}`, { immediate: true, offset: -NAV_H, force: true });
      return;
    }
    setGliding(true);
    lenis.scrollTo(`#${hash}`, {
      offset: -NAV_H,
      duration: GLIDE,
      easing: easeInOutCubic,
      lock: true,
      force: true,
      onComplete: () => {
        setGliding(false);
        setArriving(id);
        writeHash();
        window.setTimeout(() => setArriving((current) => (current === id ? null : current)), 900);
      },
    });
  };

  return <NavContext.Provider value={{ active, isGliding, arriving, glideTo }}>{children}</NavContext.Provider>;
}
