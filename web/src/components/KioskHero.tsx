import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { formatUsd } from "../lib/format";
import type { KioskScreen } from "./KioskCanvas";
import type { UpsellReplay } from "../lib/types";

const KioskCanvas = lazy(() => import("./KioskCanvas"));

const ALT = "A self-checkout kiosk showing a cart where Battery Care+ was slipped in and blocked.";

function webglOk(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function screenFrom(replay: UpsellReplay, example: boolean): KioskScreen {
  const lines = replay.without.lines.map((line) => ({
    label: line.label.replace(" · declined", ""),
    value: formatUsd(line.amount),
    trick: line.damage,
  }));
  return {
    url: replay.scene_view.checkout_url ?? replay.scene_view.cart_url,
    lines,
    latency: replay.verdict.latency_ms,
    example,
  };
}

function Still({ alt }: { alt: string }) {
  return <img src="/kiosk-hero-crop.webp" alt={alt} />;
}

export function KioskHero({ replay, example }: { replay: UpsellReplay; example: boolean }) {
  const reduced = usePrefersReducedMotion();
  const rootRef = useRef<HTMLDivElement>(null);
  const scanRef = useRef<HTMLDivElement>(null);
  const [narrow, setNarrow] = useState(() => window.matchMedia("(max-width: 767px)").matches);
  const [webgl] = useState(webglOk);
  const [lost, setLost] = useState(false);
  const screen = useMemo(() => screenFrom(replay, example), [replay, example]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 767px)");
    const onChange = () => setNarrow(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  const fallback = reduced || narrow || !webgl || lost;
  return (
    <div className="kiosk-hero" ref={rootRef} data-catch={fallback ? "still" : "wait"}>
      {fallback ? (
        <Still alt={ALT} />
      ) : (
        <Suspense fallback={<Still alt="" />}>
          <div className="kiosk-canvas" aria-hidden="true">
            <KioskCanvas screen={screen} scanRef={scanRef} rootRef={rootRef} onLost={() => setLost(true)} />
          </div>
        </Suspense>
      )}
      <div className="kiosk-scan" ref={scanRef} aria-hidden="true">
        <span className="kiosk-scan-band" />
        <span className="kiosk-scan-line" />
      </div>
    </div>
  );
}

