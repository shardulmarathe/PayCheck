import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";
import { PRODUCT_NAME } from "../lib/product";
import { EASE } from "../lib/ease";
import { TABS, type TabId } from "../hooks/useRoute";
import { usePrefersReducedMotion } from "../hooks/useReplay";

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

export function Stage({ route, children }: { route: TabId; children: ReactNode }) {
  const reduced = usePrefersReducedMotion();
  return (
    <div className="stage">
      <AnimatePresence mode="sync" initial={false}>
        <motion.div
          key={route}
          className="stage-page"
          initial={reduced ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduced ? undefined : { opacity: 0 }}
          transition={{ duration: reduced ? 0 : 0.6, ease: EASE }}
        >
          {children}
        </motion.div>
      </AnimatePresence>
    </div>
  );
}

export function ExampleMark({ show }: { show: boolean }) {
  if (!show) return null;
  return <p className="micro example-mark">example data</p>;
}
