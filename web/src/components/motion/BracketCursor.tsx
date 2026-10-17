import { useEffect, useRef, useState } from "react";
import { easeOut } from "../../lib/ease";
import { HOVER } from "../../lib/motion";
import { useLenis } from "./SmoothScroll";
import { usePrefersReducedMotion } from "../../hooks/useReplay";

const SNAP = 'a, button, [role="tab"], [data-cursor="snap"]';
const TEXT = 'input, textarea, [contenteditable="true"]';
const DUR = HOVER * 1000;

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

function finePointer(): boolean {
  return window.matchMedia("(pointer: fine)").matches && window.matchMedia("(hover: hover)").matches;
}

export function BracketCursor() {
  const reduced = usePrefersReducedMotion();
  const [active, setActive] = useState(false);

  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine)");
    const hover = window.matchMedia("(hover: hover)");
    const update = () => setActive(fine.matches && hover.matches && !reduced);
    update();
    fine.addEventListener("change", update);
    hover.addEventListener("change", update);
    return () => {
      fine.removeEventListener("change", update);
      hover.removeEventListener("change", update);
    };
  }, [reduced]);

  if (!active || !finePointer()) return null;
  return <CursorRig />;
}

function CursorRig() {
  const lenis = useLenis();
  const refs = useRef<Array<HTMLSpanElement | null>>([]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.add("cursor-none");
    const pointer = { x: -40, y: -40 };
    let snap: Element | null = null;
    let snapBox: Box | null = null;
    let hide = false;
    let inside = false;
    const current: Box = { x: -40, y: -40, w: 14, h: 14 };
    let from: Box = { ...current };
    let to: Box = { ...current };
    let started = 0;
    let animating = false;
    let frame = 0;

    const readSnap = () => {
      if (!snap) {
        snapBox = null;
        return;
      }
      const rect = snap.getBoundingClientRect();
      snapBox = { x: rect.left - 4, y: rect.top - 4, w: rect.width + 8, h: rect.height + 8 };
    };

    const begin = (next: Box) => {
      from = { ...current };
      to = next;
      started = performance.now();
      animating = true;
    };

    const apply = (box: Box) => {
      current.x = box.x;
      current.y = box.y;
      current.w = box.w;
      current.h = box.h;
      const spots = [
        [box.x, box.y],
        [box.x + box.w - 14, box.y],
        [box.x, box.y + box.h - 14],
        [box.x + box.w - 14, box.y + box.h - 14],
      ];
      refs.current.forEach((node, index) => {
        if (!node) return;
        const [x, y] = spots[index];
        node.style.transform = `translate3d(${x}px, ${y}px, 0)`;
        node.style.opacity = hide || !inside ? "0" : "1";
      });
    };

    const frameLoop = (now: number) => {
      const idle: Box = { x: pointer.x - 7, y: pointer.y - 7, w: 14, h: 14 };
      const dest = snapBox ?? idle;
      if (animating) {
        if (!snap) to = { ...idle, w: 14, h: 14 };
        else if (snapBox) to = snapBox;
        const t = Math.min(1, (now - started) / DUR);
        const e = easeOut(t);
        apply({
          x: from.x + (to.x - from.x) * e,
          y: from.y + (to.y - from.y) * e,
          w: from.w + (to.w - from.w) * e,
          h: from.h + (to.h - from.h) * e,
        });
        if (t >= 1) animating = false;
      } else {
        apply(dest);
      }
      frame = requestAnimationFrame(frameLoop);
    };
    frame = requestAnimationFrame(frameLoop);

    const onMove = (event: PointerEvent) => {
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      inside = true;
    };
    const onOver = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest(TEXT)) {
        hide = true;
        root.classList.remove("cursor-none");
        return;
      }
      if (hide) {
        hide = false;
        root.classList.add("cursor-none");
      }
      const next = target?.closest(SNAP) ?? null;
      if (next === snap) return;
      snap = next;
      readSnap();
      begin(snapBox ?? { x: pointer.x - 7, y: pointer.y - 7, w: 14, h: 14 });
    };
    const onOut = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      const next = event.relatedTarget instanceof Element ? event.relatedTarget : null;
      if (target?.closest(TEXT) && !next?.closest(TEXT)) {
        hide = false;
        root.classList.add("cursor-none");
      }
      if (!next) inside = false;
      if (snap && !next?.closest(SNAP)) {
        snap = null;
        snapBox = null;
        begin({ x: pointer.x - 7, y: pointer.y - 7, w: 14, h: 14 });
      }
    };
    const onScroll = () => {
      if (snap) readSnap();
    };

    document.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerover", onOver);
    document.addEventListener("pointerout", onOut);
    window.addEventListener("scroll", onScroll, { passive: true });
    const unsub = lenis?.on("scroll", onScroll);

    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerover", onOver);
      document.removeEventListener("pointerout", onOut);
      window.removeEventListener("scroll", onScroll);
      unsub?.();
      root.classList.remove("cursor-none");
    };
  }, [lenis]);

  return (
    <div className="bracket-cursor" aria-hidden="true">
      {["tl", "tr", "bl", "br"].map((corner, index) => (
        <span
          key={corner}
          ref={(node) => {
            refs.current[index] = node;
          }}
          className={`bc bc-${corner}`}
        />
      ))}
    </div>
  );
}
