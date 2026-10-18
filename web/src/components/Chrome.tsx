import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { PRODUCT_NAME } from "../lib/product";
import { EASE } from "../lib/ease";
import { type TabId } from "../hooks/useRoute";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { PANEL } from "../lib/motion";
import { useIntroPhase } from "./motion/Intro";
import { useNav } from "./motion/Nav";
import { useLenis } from "./motion/SmoothScroll";
import { HiddenTrick } from "./HiddenTrick";

export function TopBar({ tabs }: { tabs: readonly { id: TabId; href: string; label: string }[] }) {
  const reduced = usePrefersReducedMotion();
  const { active, glideTo } = useNav();
  const phase = useIntroPhase();
  const startedDone = useRef(phase === "done");
  const shown = phase === "done" || reduced;
  const lenis = useLenis();
  const [menu, setMenu] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!menu) return;
    lenis?.stop();
    document.documentElement.classList.add("menu-open");
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenu(false);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      lenis?.start();
      document.documentElement.classList.remove("menu-open");
      window.removeEventListener("keydown", onKey);
      menuButton.current?.focus();
    };
  }, [menu, lenis]);

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
                {tab.label}
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
        <button
          ref={menuButton}
          type="button"
          className="menu-button"
          aria-expanded={menu}
          aria-controls="menu-sheet"
          onClick={() => setMenu(true)}
        >
          Menu
        </button>
      </div>
      {menu ? (
        <div id="menu-sheet" className="menu-sheet" role="dialog" aria-modal="true" aria-label="Sections">
          <div className="wrap menu-sheet-head">
            <span className="wordmark">{PRODUCT_NAME}</span>
            <button type="button" className="menu-button menu-close" onClick={() => setMenu(false)} autoFocus>
              Close
            </button>
          </div>
          <nav className="wrap menu-links" aria-label="Sections">
            {tabs.map((tab) => (
              <a
                key={tab.id}
                href={tab.href}
                aria-current={tab.id === active ? "page" : undefined}
                onClick={(event) => {
                  event.preventDefault();
                  setMenu(false);
                  window.setTimeout(() => glideTo(tab.id as TabId), 0);
                }}
              >
                {tab.label}
              </a>
            ))}
          </nav>
        </div>
      ) : null}
    </header>
  );
}

export function Footer({ note }: { note: string }) {
  return (
    <footer className="footer">
      <div className="wrap footer-inner">
        <p className="footer-name">{PRODUCT_NAME}</p>
        {import.meta.env.DEV ? (
          /* Dev-only Battery Care+ illustration: compiled out of production builds. */
          <div className="footer-catch">
            <HiddenTrick id="footer-addon" kind="solid" label="Blocked · pre-checked add-on">
              Battery Care+ protection +$9.99
            </HiddenTrick>
            <span className="example-tag">Illustration</span>
          </div>
        ) : null}
        <a className="micro footer-link" href="https://github.com/shardulmarathe/PayCheck" target="_blank" rel="noopener noreferrer">
          GitHub
        </a>
        {note ? <p className="micro">{note}</p> : null}
      </div>
    </footer>
  );
}
