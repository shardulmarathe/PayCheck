import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { formatLatency, formatUsd } from "../lib/format";
import { replayLiftProgress } from "../lib/kioskLift";
import { kioskPose, placeKioskNow, setKioskPlacer } from "./kioskPose";
import type { KioskScreen } from "./KioskCanvas";
import { useLenis } from "./motion/SmoothScroll";
import { useNav } from "./motion/Nav";
import type { UpsellReplay } from "../lib/types";

const KioskCanvas = lazy(() => import("./KioskCanvas"));

const ALT = "A self-checkout kiosk showing a cart where Battery Care+ was slipped in and blocked.";
const ALT_QUIET = "A checkout kiosk.";

function webglOk(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function slowDevice(): boolean {
  const cores = navigator.hardwareConcurrency;
  return cores > 0 && cores <= 4;
}

export function screenFrom(replay: UpsellReplay, example: boolean, catchRate: number | null): KioskScreen {
  const quote = replay.scene_view.popup_fine_print;
  return {
    url: replay.scene_view.checkout_url ?? replay.scene_view.cart_url,
    lines: replay.without.lines.map((line) => ({
      label: line.label.replace(" · declined", ""),
      value: formatUsd(line.amount),
      trick: line.damage,
    })),
    latency: replay.verdict.latency_ms,
    example,
    quote,
    catchRate,
    readout: `Blocked · ${formatLatency(replay.verdict.latency_ms, example)}`,
    quiet: false,
  };
}

export function neutralScreen(): KioskScreen {
  return {
    url: "",
    lines: [],
    latency: null,
    example: false,
    quote: "",
    catchRate: null,
    readout: "",
    quiet: true,
  };
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function BackgroundKiosk({ screen }: { screen: KioskScreen }) {
  const reduced = usePrefersReducedMotion();
  const lenis = useLenis();
  const { active } = useNav();
  const shell = useRef<HTMLDivElement>(null);
  const scanRef = useRef<HTMLDivElement>(null);
  const [lost, setLost] = useState(false);
  const [webgl] = useState(() => webglOk() && !slowDevice());
  const quiet = screen.quiet === true;
  const fallback = reduced || !webgl || lost;
  const activeRef = useRef(active);
  activeRef.current = active;

  useEffect(() => {
    const node = shell.current;
    if (!node) return;

    const place = () => {
      const slot = document.getElementById("kiosk-slot")?.getBoundingClientRect();
      if (!slot) return;
      const narrow = window.innerWidth < 640;
      const vh = window.innerHeight;
      const vw = window.innerWidth;
      const smallH = vh * 0.22;
      const smallW = smallH * 0.72;
      const small = {
        x: vw - vw * 0.06 - smallW,
        y: vh - vh * 0.12 - smallH,
        w: smallW,
        h: smallH,
      };
      const scrolled = replayLiftProgress();
      const pull = kioskPose.cameraPull;
      const large = {
        x: vw * 0.38,
        y: vh * 0.08,
        w: Math.min(vw * 0.56, 820),
        h: vh * 0.84,
      };
      const hero = {
        x: lerp(large.x, slot.left, pull),
        y: lerp(large.y, slot.top, pull),
        w: lerp(large.w, slot.width, pull),
        h: lerp(large.h, slot.height, pull),
      };
      const poster = reduced;
      const t = poster ? (scrolled > 0.5 ? 1 : 0) : scrolled;
      const slotGone = hero.y + hero.h < 0;
      const from = slotGone ? { x: small.x, y: vh + 8, w: small.w, h: small.h } : hero;
      const box = {
        x: lerp(from.x, small.x, t),
        y: lerp(from.y, small.y, t),
        w: lerp(from.w, small.w, t),
        h: lerp(from.h, small.h, t),
      };
      const hide = narrow && t > 0.85;
      node.style.width = `${box.w}px`;
      node.style.height = `${box.h}px`;
      node.style.transform = `translate3d(${box.x}px, ${box.y}px, 0)`;
      node.style.visibility = hide ? "hidden" : "visible";

      // Brightness floor raised to 35% everywhere (was 20% next to replay/benchmarks).
      const floor = 0.35;
      kioskPose.presence = lerp(1, floor, t);
      kioskPose.yaw = poster ? 0 : scrolled * ((20 * Math.PI) / 180);
      kioskPose.invalidate();
    };

    setKioskPlacer(place);
    place();
    const onScroll = () => place();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    const unsub = lenis?.on("scroll", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      unsub?.();
      setKioskPlacer(() => {});
    };
  }, [lenis, reduced]);

  useEffect(() => {
    placeKioskNow();
  }, [active]);

  // No working 3D (no WebGL, lost context, or a blank render): hide the kiosk and center the hero text.
  useEffect(() => {
    const root = document.documentElement;
    if (fallback) root.dataset.kiosk = "off";
    else delete root.dataset.kiosk;
    return () => {
      delete root.dataset.kiosk;
    };
  }, [fallback]);

  return (
    <div ref={shell} className="bg-kiosk" aria-hidden="true">
      {fallback ? null : (
        <Suspense fallback={null}>
          <KioskCanvas screen={screen} scanRef={scanRef} onLost={() => setLost(true)} />
        </Suspense>
      )}
      <div className="trick-hotspot" data-trick-line />
      <div className="kiosk-scan" ref={scanRef}>
        <span className="kiosk-scan-band" />
        <span className="kiosk-scan-line" />
      </div>
      <p className="sr-only">{quiet ? ALT_QUIET : ALT}</p>
    </div>
  );
}
