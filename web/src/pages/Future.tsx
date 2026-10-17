import { useEffect, useRef } from "react";
import { HiddenTrick } from "../components/HiddenTrick";
import { useNav } from "../components/motion/Nav";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import type { Dataset } from "../lib/types";

export function Future({ data }: { data: Dataset }) {
  const future = data.future;
  const list = useRef<HTMLElement>(null);
  const reduced = usePrefersReducedMotion();
  const { isGliding } = useNav();

  useEffect(() => {
    const root = list.current;
    if (!root) return;
    const rows = [...root.querySelectorAll<HTMLElement>(".future-row")];
    if (reduced || isGliding) {
      root.classList.remove("will-draw");
      rows.forEach((row) => row.classList.add("is-drawn"));
      return;
    }
    root.classList.add("will-draw");
    const seen = new WeakSet<Element>();
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting || seen.has(entry.target)) return;
          seen.add(entry.target);
          entry.target.classList.add("is-drawn");
        });
      },
      { rootMargin: "0px 0px -15% 0px", threshold: 0.2 },
    );
    rows.forEach((row) => observer.observe(row));
    return () => observer.disconnect();
  }, [reduced, isGliding]);

  return (
    <div className="wrap">
      <section className="section">
        <p className="label">{future.kicker}</p>
        <h1 className="h1">
          {future.title_lines[0]}
          <br />
          {future.title_lines[1]}
        </h1>
        <p className="body-l" style={{ marginTop: 20 }}>
          {future.body}
        </p>
      </section>
      <section className="section future-list" ref={list}>
        {future.items.map((item, index) => (
          <article key={item.n} className="future-row">
            <p className="micro" data-future-first={index === 0 ? "" : undefined}>
              {item.n}
            </p>
            <div>
              <h2>{item.title}</h2>
              <p className="body">{item.body}</p>
            </div>
            <p className="micro future-status">{item.status}</p>
          </article>
        ))}
        <HiddenTrick id="future-sub" kind="solid" label="Blocked · subscription trap">
          <span className="trick-box" />
          Subscribe & save 10% · renews at $12.99/mo
        </HiddenTrick>
      </section>
    </div>
  );
}
