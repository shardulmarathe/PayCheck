import { EASE, easeOut } from "./ease";

export { EASE, easeOut };

export const HOVER = 0.15;
export const ENTER = 0.6;
export const PANEL = ENTER;
export const STAGGER = 0.12;
export const RISE = 10;
export const GLIDE = 1.1;
export const NAV_H = 56;

/** Ease-in-out for the tab glide, the intro mark flight, and the camera pull-back. */
export function easeInOutCubic(t: number): number {
  const x = Math.min(1, Math.max(0, t));
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
}
