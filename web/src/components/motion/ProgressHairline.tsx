import { useScroll } from "framer-motion";
import { useEffect, useRef } from "react";
import { useIntroPhase } from "./Intro";

export function ProgressHairline() {
  const ref = useRef<HTMLDivElement>(null);
  const phase = useIntroPhase();
  const { scrollYProgress } = useScroll();

  useEffect(() => {
    if (phase !== "done") return;
    const node = ref.current;
    if (!node) return;
    return scrollYProgress.on("change", (value) => {
      node.style.transform = `scaleX(${value})`;
    });
  }, [phase, scrollYProgress]);

  return <div id="progress-hairline" ref={ref} className="progress-hairline" aria-hidden="true" />;
}
