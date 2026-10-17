import { lazy, Suspense } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";

const KioskCanvas = lazy(() => import("./KioskCanvas"));

function KioskStill() {
  return <img src="/kiosk-still.svg" alt="" />;
}

/** Tagline companion. Reduced motion, and the canvas while it loads, use the still. */
export function KioskHero() {
  const reduced = usePrefersReducedMotion();
  return (
    <div className="kiosk-hero" aria-hidden="true">
      {reduced ? (
        <KioskStill />
      ) : (
        <Suspense fallback={<KioskStill />}>
          <KioskCanvas />
        </Suspense>
      )}
    </div>
  );
}
