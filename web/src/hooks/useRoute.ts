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
  if (path === "/" || path === "/demo") return "demo";
  if (path === "/benchmarks") return "benchmarks";
  if (path === "/design-process" || path === "/design") return "design";
  if (path === "/future" || path === "/future-improvements") return "future";
  return "demo";
}

export function useRoute(): TabId {
  const [route, setRoute] = useState<TabId>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return route;
}
