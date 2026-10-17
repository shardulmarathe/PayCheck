import { motion } from "framer-motion";
import { useRef } from "react";
import { PRODUCT_NAME } from "../lib/product";
import { EASE } from "../lib/ease";
import { type TabId } from "../hooks/useRoute";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { PANEL } from "../lib/motion";
import { useIntroPhase } from "./motion/Intro";
import { useNav } from "./motion/Nav";
import { HiddenTrick } from "./HiddenTrick";

export function TopBar({ tabs }: { tabs: readonly { id: TabId; href: string; label: string }[] }) {
  const reduced = usePrefersReducedMotion();
  const { active, glideTo } = useNav();
  const phase = useIntroPhase();
  const startedDone = useRef(phase === "done");
  const shown = phase === "done" || reduced;
  return (
    <header className={`topbar ${shown ? "" : "is-hidden"} ${startedDone.current || reduced ? "no-motion" : ""}`}>
      <div className="wrap topbar-inner">
        <a
          className="wordmark"
          href="#demo"
          onClick={(event) => {
            event.preventDefault();
            glideTo("demo");
          }}
        >
          {PRODUCT_NAME}
        </a>
        <nav className="nav" aria-label="Sections">
          {tabs.map((tab) => {
            const current = tab.id === active;
            return (
              <a
                key={tab.id}
                href={tab.href}
                aria-current={current ? "page" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  glideTo(tab.id as TabId);
                }}
              >
                {tab.id === "future" ? (
                  <>
                    <span className="nav-long">{tab.label}</span>
                    <span className="nav-short">Future</span>
                  </>
                ) : (
                  tab.label
                )}
                {current ? (
                  <motion.span
                    layoutId="tab-underline"
                    className="nav-underline"
                    transition={{ duration: reduced ? 0 : PANEL, ease: EASE }}
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
        <HiddenTrick id="footer-fee" kind="solid" label="Blocked · drip fee">
          Service fee +$1.49
        </HiddenTrick>
        <p className="micro">{note}</p>
      </div>
    </footer>
  );
}

export function ExampleMark({ show }: { show: boolean }) {
  if (!show) return null;
  return <p className="micro example-mark">example data</p>;
}
