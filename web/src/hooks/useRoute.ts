import { useEffect, useState } from "react";

export const TABS = [
  { id: "demo", href: "#/", label: "Demo" },
  { id: "benchmarks", href: "#/benchmarks", label: "Benchmarks" },
  { id: "design", href: "#/design-process", label: "Design process" },
  { id: "future", href: "#/future", label: "Future improvements" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export function parseHash(hash: string): TabId {
  const path = hash.replace(/^#/, "").replace(/\/$/, "") || "/";
  if (path === "/" || path === "/demo" || path === "/replay-2" || path === "replay-2") return "demo";
  if (path === "/benchmarks") return "benchmarks";
  if (path === "/design-process" || path === "/design") return "design";
  if (path === "/future" || path === "/future-improvements") return "future";
  return "demo";
}

export type ReplayChoice = 1 | 2;

export function parseReplay(hash: string): ReplayChoice {
  const path = hash.replace(/^#/, "").replace(/\/$/, "");
  if (path === "/replay-2" || path === "replay-2") return 2;
  return 1;
}

export function useReplayChoice(): [ReplayChoice, (next: ReplayChoice) => void] {
  const [choice, setChoice] = useState<ReplayChoice>(() => parseReplay(window.location.hash));

  useEffect(() => {
    const onChange = () => setChoice(parseReplay(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const select = (next: ReplayChoice) => {
    const hash = next === 2 ? "#/replay-2" : "#/";
    if (window.location.hash !== hash) window.location.hash = hash;
    setChoice(next);
  };

  return [choice, select];
}

export function useRoute(): TabId {
  const [route, setRoute] = useState<TabId>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => {
      const next = parseHash(window.location.hash);
      setRoute((prev) => {
        if (prev !== next) window.scrollTo(0, 0);
        return next;
      });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}
