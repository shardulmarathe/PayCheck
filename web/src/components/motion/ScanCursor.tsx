import { useEffect } from "react";

/**
 * Site-wide scanner cursor (fine pointers only, never under reduced motion).
 * The crosshair centre is drawn exactly at the pointer on every move (no smoothing), so click accuracy is unchanged;
 * only the outer ring trails a little. Hovering a control or a trick field locks on: corner brackets snap around it
 * with a small mono readout. Text inputs keep the native cursor.
 * Also drives the 2.5D tilt of cards toward the pointer.
 */
const LOCK = "a, button, [role='tab'], summary, .tc-item, .ts-content > .ts-target, .kz-form, [data-scan]";
const TILT = ".how-step, .speed-stat, .tc-card, .tap-term, .race, .fv-device, .hero-compare > div, .pl-node, .tap-node";

export function ScanCursor() {
  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine)").matches;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!fine || reduced) return;
    const root = document.documentElement;
    root.classList.add("scan-cursor");

    const layer = document.createElement("div");
    layer.className = "sc";
    layer.setAttribute("aria-hidden", "true");
    layer.innerHTML =
      '<div class="sc-dot"><i></i><i></i><i></i><i></i><b></b></div><div class="sc-ring"></div>' +
      '<div class="sc-lock"><i></i><i></i><i></i><i></i><span class="sc-read">Inspecting</span></div>';
    document.body.appendChild(layer);
    const dot = layer.querySelector<HTMLElement>(".sc-dot")!;
    const ring = layer.querySelector<HTMLElement>(".sc-ring")!;
    const lock = layer.querySelector<HTMLElement>(".sc-lock")!;
    const read = layer.querySelector<HTMLElement>(".sc-read")!;

    let x = -100;
    let y = -100;
    let rx = -100;
    let ry = -100;
    let target: Element | null = null;
    let tilted: HTMLElement | null = null;
    let frame = 0;
    let shown = false;

    const place = () => {
      if (target && target.isConnected) {
        const r = target.getBoundingClientRect();
        const pad = 6;
        lock.style.transform = `translate3d(${r.left - pad}px, ${r.top - pad}px, 0)`;
        lock.style.width = `${r.width + pad * 2}px`;
        lock.style.height = `${r.height + pad * 2}px`;
      }
    };

    const tick = () => {
      rx += (x - rx) * 0.22;
      ry += (y - ry) * 0.22;
      ring.style.transform = `translate3d(${rx}px, ${ry}px, 0)`;
      place();
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    const untilt = () => {
      if (!tilted) return;
      tilted.style.transform = "";
      tilted.classList.remove("is-tilting");
      tilted = null;
    };

    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== "mouse" && e.pointerType !== "pen") return;
      x = e.clientX;
      y = e.clientY;
      dot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      if (!shown) {
        shown = true;
        layer.classList.add("is-on");
      }
      const el = e.target instanceof Element ? e.target : null;
      const text = el?.closest("input, textarea, select, [contenteditable='true']");
      layer.classList.toggle("is-text", !!text);
      const next = text ? null : el?.closest(LOCK) ?? null;
      if (next !== target) {
        target = next;
        if (target) {
          const label = (target as HTMLElement).dataset?.scanLabel;
          read.textContent = label ?? (target.matches(".tc-item, .ts-target, .kz-form") ? "Held · trick found" : "Inspecting");
          layer.classList.toggle("is-trick", target.matches(".tc-item, .ts-target, .kz-form"));
          lock.classList.remove("is-on");
          place();
          void lock.offsetWidth;
          lock.classList.add("is-on");
        } else lock.classList.remove("is-on");
      }
      // 2.5D tilt toward the pointer.
      const card = el?.closest<HTMLElement>(TILT) ?? null;
      if (card !== tilted) untilt();
      if (card) {
        tilted = card;
        const r = card.getBoundingClientRect();
        const nx = (x - r.left) / r.width - 0.5;
        const ny = (y - r.top) / r.height - 0.5;
        card.classList.add("is-tilting");
        card.style.transform = `perspective(900px) rotateX(${(-ny * 7).toFixed(2)}deg) rotateY(${(nx * 9).toFixed(2)}deg) translateZ(6px)`;
        card.style.setProperty("--mx", `${((nx + 0.5) * 100).toFixed(1)}%`);
        card.style.setProperty("--my", `${((ny + 0.5) * 100).toFixed(1)}%`);
      }
    };
    const onLeave = () => {
      shown = false;
      layer.classList.remove("is-on");
      untilt();
    };
    const onDown = () => layer.classList.add("is-down");
    const onUp = () => layer.classList.remove("is-down");

    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("pointerup", onUp);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointerup", onUp);
      untilt();
      layer.remove();
      root.classList.remove("scan-cursor");
    };
  }, []);
  return null;
}
