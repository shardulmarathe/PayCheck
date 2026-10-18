export type KioskMode = "demo" | "benchmarks" | "design" | "future";

/** Imperative pose for the one kiosk. Scroll and the intro write it; the canvas reads it. */
export const kioskPose = {
  zoom: 1,
  bezelHidden: false,
  presence: 1,
  yaw: 0,
  cameraPull: 1,
  mode: "demo" as KioskMode,
  modeFrom: "demo" as KioskMode,
  modeMix: 1,
  sweep: 1,
  bracket: 1,
  settle: 1,
  glow: 0,
  readout: 1,
  /** True once the 3D kiosk has drawn its first frame (or the flat fallback is up). */
  ready: false,
  invalidate: () => {},
};

let readyWaiters: (() => void)[] = [];

export function markKioskReady() {
  if (kioskPose.ready) return;
  kioskPose.ready = true;
  const waiters = readyWaiters;
  readyWaiters = [];
  for (const fn of waiters) fn();
}

/** Calls fn once the kiosk can be seen. Returns an unsubscribe. */
export function whenKioskReady(fn: () => void): () => void {
  if (kioskPose.ready) {
    fn();
    return () => {};
  }
  readyWaiters.push(fn);
  return () => {
    readyWaiters = readyWaiters.filter((w) => w !== fn);
  };
}

let place = () => {};

export function setKioskPlacer(fn: () => void) {
  place = fn;
}

export function placeKioskNow() {
  place();
}
