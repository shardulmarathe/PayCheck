import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { PRODUCT_NAME } from "../lib/product";
import { EASE } from "../lib/ease";
import { TABS, type TabId } from "../hooks/useRoute";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { useCut, type CutPhase } from "../hooks/useCut";

export function TopBar({ route }: { route: TabId }) {
  const reduced = usePrefersReducedMotion();
  return (
    <header className="topbar">
      <div className="wrap topbar-inner">
        <a className="wordmark" href="#/">
          {PRODUCT_NAME}
        </a>
        <nav className="nav" aria-label="Sections">
          {TABS.map((tab) => {
            const current = tab.id === route;
            return (
              <a key={tab.id} href={tab.href} aria-current={current ? "page" : undefined}>
                {tab.label}
                {current ? (
                  <motion.span
                    layoutId="tab-underline"
                    className="nav-underline"
                    transition={{ duration: reduced ? 0 : 0.7, ease: EASE }}
                  />
                ) : null}
              </a>
            );
          })}
        </nav>
      </div>
    </header>
  );
}

export function Footer({ note }: { note: string }) {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <p className="footer-name">{PRODUCT_NAME}</p>
        <p className="micro">{note}</p>
      </div>
    </footer>
  );
}

export function Shutter({ phase }: { phase: CutPhase }) {
  if (phase === "idle") return null;
  return (
    <div className={`shutter ${phase}`} aria-hidden="true">
      <div className="shutter-scan">
        <span className="shutter-band" />
        <span className="shutter-line" />
      </div>
    </div>
  );
}

export function Stage({ route, children }: { route: TabId; children: (shown: TabId) => ReactNode }) {
  const { shown, phase } = useCut(route);
  return (
    <div className="stage">
      <div className="stage-page">{children(shown)}</div>
      <Shutter phase={phase} />
    </div>
  );
}

export function ExampleMark({ show }: { show: boolean }) {
  if (!show) return null;
  return <p className="micro example-mark">example data</p>;
}
