import { useEffect } from "react";
import { Footer, Stage, TopBar } from "./components/Chrome";
import { getDataset } from "./data/dataset";
import { TABS, useRoute } from "./hooks/useRoute";
import { PRODUCT_NAME } from "./lib/product";
import { Benchmarks } from "./pages/Benchmarks";
import { Demo } from "./pages/Demo";
import { DesignProcess } from "./pages/DesignProcess";
import { Future } from "./pages/Future";

const data = getDataset();

export function App() {
  const route = useRoute();
  useEffect(() => {
    const tab = TABS.find((item) => item.id === route);
    document.title = route === "demo" || !tab ? PRODUCT_NAME : `${PRODUCT_NAME} · ${tab.label}`;
  }, [route]);

  return (
    <>
      <a className="skip" href="#content">
        Skip to content
      </a>
      <TopBar route={route} />
      <main id="content" tabIndex={-1}>
        <Stage route={route}>
          {(shown) => (
            <>
              {shown === "demo" ? <Demo data={data} /> : null}
              {shown === "benchmarks" ? <Benchmarks data={data} /> : null}
              {shown === "design" ? <DesignProcess data={data} /> : null}
              {shown === "future" ? <Future data={data} /> : null}
            </>
          )}
        </Stage>
      </main>
      <Footer note={data.footer_note} />
    </>
  );
}
