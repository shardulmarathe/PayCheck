import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { useNav } from "./motion/Nav";

const KEY = "sureshopCaught";

function TrickCorners({ tone, dashed }: { tone: "red" | "white"; dashed: boolean }) {
  const stroke = tone === "red" ? "#FF453A" : "#EEF1F5";
  const dash = dashed ? "4 3" : undefined;
  const paths = ["M9 1 H1 V9", "M1 1 H9 V9", "M9 9 H1 V1", "M1 9 H9 V1"];
  return (
    <span className={`ht-set ht-${tone}`}>
      {paths.map((d) => (
        <svg key={d} viewBox="0 0 10 10" aria-hidden="true">
          <path d={d} fill="none" stroke={stroke} strokeWidth="1.5" strokeDasharray={dash} />
        </svg>
      ))}
    </span>
  );
}

function readCaught(): string[] {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function remember(id: string) {
  const next = new Set(readCaught());
  next.add(id);
  try {
    sessionStorage.setItem(KEY, JSON.stringify([...next]));
  } catch {
    /* private mode */
  }
}

/**
 * A small checkout trick the page catches once it is actually on screen.
 * Decorative: it is not a result, a control, or part of the recorded data.
 */
export function HiddenTrick({
  id,
  kind,
  label,
  children,
}: {
  id: string;
  kind: "solid" | "dashed";
  label: string;
  children: ReactNode;
}) {
  const reduced = usePrefersReducedMotion();
  const { isGliding } = useNav();
  const ref = useRef<HTMLDivElement>(null);
  const visible = useRef(false);
  const gliding = useRef(isGliding);
  gliding.current = isGliding;
  const [state, setState] = useState<"idle" | "play" | "done">(() =>
    reduced || readCaught().includes(id) ? "done" : "idle",
  );

  useEffect(() => {
    if (state !== "idle") return;
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible.current = !!entry?.isIntersecting && entry.intersectionRatio >= 0.6;
        if (visible.current && !gliding.current) {
          remember(id);
          setState("play");
        }
      },
      { threshold: [0, 0.6, 1] },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [id, state]);

  useEffect(() => {
    if (state === "idle" && !isGliding && visible.current) {
      remember(id);
      setState("play");
    }
  }, [id, isGliding, state]);

  useEffect(() => {
    if (state !== "play") return;
    const timer = window.setTimeout(() => setState("done"), 1400);
    return () => window.clearTimeout(timer);
  }, [state]);

  return (
    <div ref={ref} className={`hidden-trick is-${state} is-${kind}`} aria-hidden="true">
      <div className="hidden-trick-body">
        <span className="hidden-trick-copy">{children}</span>
        <TrickCorners tone="red" dashed={kind === "dashed"} />
        <TrickCorners tone="white" dashed={kind === "dashed"} />
      </div>
      <p className="hidden-trick-label">{label}</p>
    </div>
  );
}
