import { MotionConfig } from "framer-motion";
import { BackgroundKiosk, neutralScreen, screenFrom } from "./components/BackgroundKiosk";
import { Footer, TopBar } from "./components/Chrome";
import { LiftCarrier } from "./components/LiftCarrier";
import { StoryCarriers } from "./components/StoryCarriers";
import { IntroProvider, useIntroPhase } from "./components/motion/Intro";
import { NavProvider, useNav } from "./components/motion/Nav";
import { ProgressHairline } from "./components/motion/ProgressHairline";
import { SmoothScroll } from "./components/motion/SmoothScroll";
import { getDataset } from "./data/dataset";
import { EASE, ENTER } from "./lib/motion";
import { Benchmarks } from "./pages/Benchmarks";
import { Demo } from "./pages/Demo";
import { DesignProcess } from "./pages/DesignProcess";
import { Future } from "./pages/Future";
import { TABS } from "./hooks/useRoute";
import type { UpsellReplay } from "./lib/types";

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
  const phase = useIntroPhase();
  const upsell = data.shown.replays
    ? data.replays.find((replay): replay is UpsellReplay => replay.scene === "upsell")
    : undefined;
  const guard = data.models.find((model) => model.emphasis);
  const screen = upsell
    ? screenFrom(upsell, data.example.replays, data.shown.benchmarks ? (guard?.catch_rate ?? null) : null)
    : neutralScreen();
  const tabs = TABS.filter((tab) => tab.id !== "benchmarks" || data.shown.benchmarks);
  const dimmed = phase === "catch";

  return (
    <>
      <BackgroundKiosk screen={screen} />
      <ProgressHairline />
      <TopBar tabs={tabs} />
      <main id="content" className="page" tabIndex={-1} style={{ opacity: dimmed ? 0.28 : 1 }}>
        <a className="skip" href="#content">
          Skip to content
        </a>
        <section id="demo" data-tab="demo" data-arrive={arriving === "demo" ? "1" : undefined}>
          <Demo data={data} />
        </section>
        {data.shown.benchmarks ? (
          <section id="benchmarks" data-tab="benchmarks" data-arrive={arriving === "benchmarks" ? "1" : undefined}>
            <Benchmarks data={data} />
          </section>
        ) : null}
        <section id="design-process" data-tab="design" data-arrive={arriving === "design" ? "1" : undefined}>
          <DesignProcess data={data} />
        </section>
        <section id="future" data-tab="future" data-arrive={arriving === "future" ? "1" : undefined}>
          <Future data={data} />
        </section>
        <Footer note={data.footer_note} />
      </main>
      {upsell ? <LiftCarrier label={upsell.scene_view.popup_fine_print} /> : null}
      <StoryCarriers />
    </>
  );
}
