import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { easeOut } from "../../lib/ease";
import { easeInOutCubic, PANEL } from "../../lib/motion";
import { PRODUCT_NAME } from "../../lib/product";
import { kioskPose, placeKioskNow } from "../kioskPose";

export type IntroPhase = "loader" | "flight" | "catch" | "pullback" | "done";

const IntroContext = createContext<IntroPhase>("done");

export function useIntroPhase(): IntroPhase {
  return useContext(IntroContext);
}

function landingHash(hash: string): boolean {
  const path = hash.replace(/^#/, "").replace(/\/$/, "");
  return path === "" || path === "/" || path === "demo" || path === "/demo" || path === "replay-2" || path === "/replay-2";
}

function reducedNow(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function introSeen(): boolean {
  try {
    return sessionStorage.getItem("sureshopIntro") === "1";
  } catch {
    return false;
  }
}

function markIntroSeen() {
  try {
    sessionStorage.setItem("sureshopIntro", "1");
  } catch {
    /* private mode */
  }
}

function initialPhase(): IntroPhase {
  if (reducedNow() || introSeen() || !landingHash(window.location.hash)) return "done";
  return "loader";
}

function settlePose() {
  kioskPose.cameraPull = 1;
  kioskPose.sweep = 1;
  kioskPose.bracket = 1;
  kioskPose.settle = 1;
  kioskPose.glow = 0;
  kioskPose.readout = 1;
  kioskPose.invalidate();
  placeKioskNow();
}

export function IntroProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<IntroPhase>(() => {
    const next = initialPhase();
    if (next !== "done") {
      kioskPose.cameraPull = 0;
      kioskPose.sweep = 0;
      kioskPose.bracket = 0;
      kioskPose.settle = 0;
      kioskPose.glow = 0;
      kioskPose.readout = 0;
    }
    return next;
  });

  useEffect(() => {
    if (phase === "done") {
      settlePose();
      markIntroSeen();
      return;
    }
    // The clock starts once. Phase changes must not restart the four seconds.
    const t0 = performance.now();
    let frame = 0;
    let stopped = false;
    let current: IntroPhase = "loader";

    const detach = () => {
      window.removeEventListener("wheel", skip);
      window.removeEventListener("touchstart", skip);
      window.removeEventListener("pointerdown", skip);
      window.removeEventListener("keydown", skip);
    };

    const finish = () => {
      if (stopped) return;
      stopped = true;
      cancelAnimationFrame(frame);
      detach();
      settlePose();
      markIntroSeen();
      current = "done";
      setPhase("done");
    };

    const skip = () => {
      finish();
    };

    window.addEventListener("wheel", skip, { passive: true });
    window.addEventListener("touchstart", skip, { passive: true });
    window.addEventListener("pointerdown", skip);
    window.addEventListener("keydown", skip);

    const tick = (now: number) => {
      if (stopped) return;
      const elapsed = now - t0;
      let next: IntroPhase = "done";
      if (elapsed < 700) next = "loader";
      else if (elapsed < 1600) next = "flight";
      else if (elapsed < 3000) next = "catch";
      else if (elapsed < 4000) next = "pullback";
      if (next !== current) {
        current = next;
        setPhase(next);
      }

      const catchT = elapsed - 1600;
      if (elapsed < 1600) {
        kioskPose.cameraPull = 0;
        kioskPose.sweep = 0;
        kioskPose.bracket = 0;
        kioskPose.settle = 0;
        kioskPose.glow = 0;
        kioskPose.readout = 0;
      } else if (elapsed < 3000) {
        kioskPose.cameraPull = 0;
        kioskPose.sweep = Math.min(1, Math.max(0, catchT / 700));
        const lockAt = 460;
        kioskPose.bracket = easeOut(Math.min(1, Math.max(0, (catchT - lockAt) / 400)));
        kioskPose.readout = easeOut(Math.min(1, Math.max(0, (catchT - lockAt - 400) / 250)));
        kioskPose.settle = easeOut(Math.min(1, Math.max(0, (catchT - lockAt - 650) / 500)));
        kioskPose.glow = kioskPose.bracket * (1 - kioskPose.settle);
      } else {
        kioskPose.cameraPull = easeInOutCubic((elapsed - 3000) / 1000);
        kioskPose.sweep = 1;
        kioskPose.bracket = 1;
        kioskPose.settle = 1;
        kioskPose.glow = 0;
        kioskPose.readout = 1;
      }

      const loader = document.getElementById("intro-loader");
      if (loader) {
        const fade = elapsed < 700 ? 1 : Math.max(0, 1 - (elapsed - 700) / (PANEL * 1000));
        loader.style.opacity = String(fade);
      }
      const mark = document.getElementById("intro-mark");
      const target = document.querySelector("[data-trick-line]")?.getBoundingClientRect();
      if (mark) {
        const fromX = window.innerWidth / 2 - 32;
        const fromY = window.innerHeight / 2 - 8;
        if (elapsed < 700 || !target) {
          mark.style.opacity = "1";
          mark.style.transform = `translate3d(${fromX}px, ${fromY}px, 0) scale(1)`;
        } else if (elapsed < 1600) {
          const p = easeInOutCubic((elapsed - 700) / 900);
          const x = fromX + (target.left - fromX) * p;
          const y = fromY + (target.top - fromY) * p;
          const scale = 1 + (target.width / 64 - 1) * p;
          mark.style.opacity = "1";
          mark.style.transform = `translate3d(${x}px, ${y}px, 0) scale(${scale})`;
        } else {
          mark.style.opacity = "0";
        }
      }
      const bar = document.getElementById("progress-hairline");
      if (bar && elapsed < 4000) bar.style.transform = `scaleX(${Math.min(1, elapsed / 4000)})`;

      placeKioskNow();
      kioskPose.invalidate();
      if (elapsed >= 4000) {
        finish();
        return;
      }
      frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => {
      stopped = true;
      cancelAnimationFrame(frame);
      detach();
    };
    // phase is the value from the first render. Restarting this clock would replay the intro.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <IntroContext.Provider value={phase}>
      {children}
      {phase === "done" ? null : <IntroOverlay />}
    </IntroContext.Provider>
  );
}

function IntroOverlay() {
  return (
    <>
      <div id="intro-loader" className="intro-loader">
        <p className="intro-word">{PRODUCT_NAME}</p>
      </div>
      <div id="intro-mark" className="intro-mark" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </div>
    </>
  );
}
