import { useEffect } from "react";

export function useSectionReveal(): void {
  useEffect(() => {
    const root = document.documentElement;
    const targets = [...document.querySelectorAll<HTMLElement>("main.v10 > section:not(#demo) .section")];
    if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    root.classList.add("reveal-on");
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.classList.add("is-in");
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.05 },
    );
    for (const target of targets) {
      [...target.children].forEach((child, index) => (child as HTMLElement).style.setProperty("--i", String(Math.min(index, 6))));
      // Already on screen (deep link or reload mid-page): show without animating.
      const rect = target.getBoundingClientRect();
      if (rect.top < window.innerHeight && rect.bottom > 0) target.classList.add("is-in", "no-anim");
      else observer.observe(target);
    }
    return () => observer.disconnect();
  }, []);
}
