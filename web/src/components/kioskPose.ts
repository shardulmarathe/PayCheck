export type KioskMode = "demo" | "benchmarks" | "design" | "future";

/** Imperative pose for the one kiosk. Scroll and the intro write it; the canvas reads it. */
export const kioskPose = {
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
  invalidate: () => {},
};

let place = () => {};

export function setKioskPlacer(fn: () => void) {
  place = fn;
}

export function placeKioskNow() {
  place();
}
