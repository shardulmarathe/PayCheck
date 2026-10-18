import { MotionConfig } from "framer-motion";
import { Footer, TopBar } from "./components/Chrome";
import { IntroProvider } from "./components/motion/Intro";
import { ScanCursor } from "./components/motion/ScanCursor";
import { useSectionReveal } from "./hooks/useSectionReveal";
import { NavProvider, useNav } from "./components/motion/Nav";
import { ProgressHairline } from "./components/motion/ProgressHairline";
import { SmoothScroll } from "./components/motion/SmoothScroll";
import { getDataset } from "./data/dataset";
import { EASE, ENTER } from "./lib/motion";
import { Trained, WhyBetter } from "./components/Accuracy";
import { Evidence } from "./components/Evidence";
import { HowItWorks } from "./components/HowItWorks";
import { SeeItWork } from "./components/RunTest";
import { Coach } from "./components/Coach";
import { VisaSection } from "./components/VisaTrace";
import { Demo } from "./pages/Demo";
import { Future } from "./pages/Future";
import { TABS } from "./hooks/useRoute";

const data = getDataset();

export function App() {
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: ENTER, ease: [...EASE] }}>
      <IntroProvider>
        <SmoothScroll>
          <NavProvider>
            <Site />
          </NavProvider>
        </SmoothScroll>
      </IntroProvider>
    </MotionConfig>
  );
}

function Site() {
  const { arriving } = useNav();
  const tabs = TABS.filter((tab) => tab.id !== "visa" || data.visa.length > 0);
  const arrive = (id: string) => (arriving === id ? "1" : undefined);
  useSectionReveal();

  return (
    <>
      <a className="skip" href="#content">
        Skip to content
      </a>
      <ScanCursor />
      <ProgressHairline />
      <TopBar tabs={tabs} />
      <main id="content" className="page v10 flow18" tabIndex={-1}>
        <section id="demo" data-tab="demo" data-arrive={arrive("demo")} aria-label="The problem">
          <Evidence />
        </section>
        <section id="paycheck" data-tab="paycheck" data-arrive={arrive("paycheck")}>
          <Demo data={data} />
        </section>
        <section id="how-it-works" data-tab="how" data-arrive={arrive("how")}>
          <HowItWorks />
        </section>
        <section id="why" data-tab="why" data-arrive={arrive("why")}>
          <WhyBetter models={data.models} />
        </section>
        <section id="see-it-work" data-tab="see" data-arrive={arrive("see")}>
          <SeeItWork />
        </section>
        <section id="coach" data-tab="coach" data-arrive={arrive("coach")}>
          <Coach />
        </section>
        <section id="trained" data-tab="trained" data-arrive={arrive("trained")}>
          <Trained />
        </section>
        {data.visa.length ? (
          <section id="visa" data-tab="visa" data-arrive={arrive("visa")}>
            <VisaSection traces={data.visa} />
          </section>
        ) : null}
        <section id="future" data-tab="future" data-arrive={arrive("future")}>
          <Future data={data} />
        </section>
      </main>
      <Footer note={data.footer_note} />
    </>
  );
}
