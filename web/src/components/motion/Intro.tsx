import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { PANEL } from "../../lib/motion";
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
  // Round 18: the kiosk hero was cut, so there is no intro to play.
  void reducedNow; void introSeen; void landingHash;
  return "done";
}

function settlePose() {
  // The camera zoom belongs to HeroKiosk (it waits for the 3D kiosk to be drawn); the intro only settles the rest.
  kioskPose.cameraPull = 1;
  kioskPose.sweep = 1;
  kioskPose.bracket = 1;
  kioskPose.settle = 1;
  kioskPose.glow = 0;
  kioskPose.readout = 1;
  kioskPose.invalidate();
  placeKioskNow();
}

/** Overshoot ease for the bracket snap (back-out, gentle). */
function easeOutBack(t: number): number {
  const x = Math.min(1, Math.max(0, t));
  const c1 = 1.9;
  const c3 = c1 + 1;
  return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
}

function easeOutCubic(t: number): number {
  const x = Math.min(1, Math.max(0, t));
  return 1 - (1 - x) ** 3;
}

interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** The kiosk screen's on-page box (the canvas keeps .kz-screen on the projected screen every frame). */
function targetBox(): Box | null {
  const screen = document.querySelector<HTMLElement>(".kz-screen")?.getBoundingClientRect();
  if (screen && screen.width > 12 && screen.height > 12) return screen;
  return document.querySelector("[data-trick-line]")?.getBoundingClientRect() ?? null;
}

// Phase lengths (ms) after the loader: brackets fly in, lock on, then the camera dolly (HeroKiosk) runs.
const LOADER_MIN = 700;
const LOADER_MAX_WAIT = 2600; // extra wait for the 3D kiosk chunk before going ahead without it
const FLIGHT = 560;
const LOCK = 520;
const ZOOM = 1900;
const PULLBACK = 320;

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
    // The clock starts once. Phase changes must not restart it.
    const t0 = performance.now();
    let frame = 0;
    let stopped = false;
    let current: IntroPhase = "loader";
    let loaderEnd = -1;

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

    const corners = () => [...document.querySelectorAll<HTMLElement>("#intro-mark i")];

    const tick = (now: number) => {
      if (stopped) return;
      const elapsed = now - t0;
      // Hold the loader until the 3D kiosk has drawn (or we stop waiting), so the zoom is never missed.
      if (loaderEnd < 0 && elapsed >= LOADER_MIN && (kioskPose.ready || elapsed >= LOADER_MIN + LOADER_MAX_WAIT)) {
        loaderEnd = elapsed;
      }
      const since = loaderEnd < 0 ? -1 : elapsed - loaderEnd;
      const flightEnd = FLIGHT;
      const lockEnd = FLIGHT + LOCK;
      const zoomEnd = lockEnd + ZOOM;
      const doneAt = zoomEnd + PULLBACK;
      let next: IntroPhase = "done";
      if (since < 0) next = "loader";
      else if (since < lockEnd) next = "flight";
      else if (since < zoomEnd) next = "catch";
      else if (since < doneAt) next = "pullback";
      if (next !== current) {
        current = next;
        setPhase(next);
      }

      const loader = document.getElementById("intro-loader");
      if (loader) {
        const fade = since < 0 ? 1 : Math.max(0, 1 - since / (PANEL * 1000));
        loader.style.opacity = String(fade);
      }

      // Brackets: four thin corners, no scaling. They snap in from the viewport corners with a short overshoot,
      // lock onto the kiosk screen (glow pulse + scan sweep), then release outward and fade as the camera moves in.
      const mark = document.getElementById("intro-mark");
      const box = targetBox();
      if (mark && box) {
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const arm = vw < 600 ? 14 : 20;
        const inset = 28;
        const starts = [
          [inset, inset],
          [vw - inset, inset],
          [inset, vh - inset],
          [vw - inset, vh - inset],
        ];
        const pad = 6;
        let release = 0;
        if (since >= lockEnd) release = easeOutCubic((since - lockEnd) / 380);
        const out = pad + release * 18;
        const ends = [
          [box.left - out, box.top - out],
          [box.left + box.width + out, box.top - out],
          [box.left - out, box.top + box.height + out],
          [box.left + box.width + out, box.top + box.height + out],
        ];
        mark.style.opacity = since < 0 ? "0" : String(1 - release);
        mark.dataset.lock = since >= flightEnd && since < lockEnd + 380 ? "1" : "0";
        corners().forEach((corner, i) => {
          const local = since < 0 ? 0 : easeOutBack((since - i * 45) / (FLIGHT - 3 * 45));
          const x = starts[i][0] + (ends[i][0] - starts[i][0]) * local;
          const y = starts[i][1] + (ends[i][1] - starts[i][1]) * local;
          const len = arm * (0.45 + 0.55 * Math.min(1, Math.max(0, local)));
          corner.style.width = `${len}px`;
          corner.style.height = `${len}px`;
          const dx = i % 2 === 0 ? 0 : -len;
          const dy = i < 2 ? 0 : -len;
          corner.style.transform = `translate3d(${x + dx}px, ${y + dy}px, 0)`;
        });
        const scan = document.getElementById("intro-scan");
        const glow = document.getElementById("intro-glow");
        const lockP = since < flightEnd ? -1 : (since - flightEnd) / LOCK;
        if (glow) {
          glow.style.transform = `translate3d(${box.left}px, ${box.top}px, 0)`;
          glow.style.width = `${box.width}px`;
          glow.style.height = `${box.height}px`;
          glow.style.opacity = lockP < 0 ? "0" : String(Math.max(0, 1 - lockP) * (lockP < 0.12 ? lockP / 0.12 : 1));
        }
        if (scan) {
          const sp = lockP < 0 ? 0 : easeOutCubic(Math.min(1, lockP / 0.85));
          scan.style.transform = `translate3d(${box.left}px, ${box.top + sp * box.height}px, 0)`;
          scan.style.width = `${box.width}px`;
          scan.style.opacity = lockP < 0 || lockP > 1 ? "0" : String(1 - Math.max(0, (lockP - 0.7) / 0.3));
        }
      }
      const bar = document.getElementById("progress-hairline");
      if (bar && current !== "done") bar.style.transform = `scaleX(${Math.min(1, elapsed / LOADER_MIN)})`;

      placeKioskNow();
      kioskPose.invalidate();
      if (since >= doneAt) {
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
    // Runs once: restarting this clock would replay the intro.
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
      <div id="intro-mark" className="intro-mark" aria-hidden="true" data-lock="0">
        <i />
        <i />
        <i />
        <i />
        <span id="intro-glow" className="intro-glow" />
        <span id="intro-scan" className="intro-scan" />
      </div>
    </>
  );
}
