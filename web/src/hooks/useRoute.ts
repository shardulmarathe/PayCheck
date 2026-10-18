import { useEffect, useState } from "react";

export const TABS = [
  { id: "demo", href: "#demo", label: "The problem" },
  { id: "paycheck", href: "#paycheck", label: "Meet PayCheck" },
  { id: "how", href: "#how-it-works", label: "How it works" },
  { id: "why", href: "#why", label: "Why it's better" },
  { id: "see", href: "#see-it-work", label: "See it work" },
  { id: "coach", href: "#coach", label: "Coach" },
  { id: "trained", href: "#trained", label: "How we trained it" },
  { id: "visa", href: "#visa", label: "Payments" },
  { id: "future", href: "#future", label: "What's next" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export const TAB_IDS: readonly TabId[] = TABS.map((tab) => tab.id);

/** Element id the tab glides to. */
export function sectionId(tab: TabId): string {
  return TABS.find((t) => t.id === tab)!.href.slice(1);
}

export function tabFromHash(hash: string): TabId {
  const path = hash.replace(/^#/, "").replace(/^\//, "").replace(/\/$/, "");
  const hit = TABS.find((t) => t.href.slice(1) === path || t.id === path);
  if (hit) return hit.id;
  if (path === "accuracy" || path === "results") return "why";
  if (path === "try-it" || path === "try") return "see";
  if (path === "payments") return "visa";
  return "demo";
}

export function parseHash(hash: string): TabId {
  return tabFromHash(hash);
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
    const hash = next === 2 ? "#replay-2" : "#demo";
    if (window.location.hash !== hash) window.history.replaceState(null, "", hash);
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
