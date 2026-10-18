import type { MotionValue } from "framer-motion";
import { useDriver } from "./motion/Pin";

/**
 * How PayCheck was built, as a pipeline that lights up stage by stage with particles flowing between stages.
 * Every line restates site copy or /workspace/final/PROVISIONAL-FINAL.md in plain words:
 * practice stores with honest twins (howSteps[1]); trick text from ec-darkpattern / Mathur et al. (accuracyOrigin);
 * test pages split off before training (accuracyOrigin; 300 pages, half tricks: accuracyTest);
 * Qwen3-4B trained with veri.studio (builtWith; PF:400–402 Veri datasets); 300 attacker-written pages,
 * half tricks, half honest (PF:401); picked on development pages, never on the test (PF:384, site-sections node 04);
 * graded once on the locked benchmark (no score shown: benchmark scores appear only where PayCheck wins). The stage text is readable (not aria-hidden):
 * it is the one place the method and the page sources are stated (de-duplicated, round 14).
 */
const STAGES = [
  { k: "01", title: "Practice stores", body: "Generated stores, each hiding one trick next to an honest twin. Trick text from the ec-darkpattern dataset, built on Mathur et al., \"Dark Patterns at Scale\" (Princeton, 2019)." },
  { k: "02", title: "Test pages locked away", body: "300 checkout pages, half with a hidden trick, half honest, split off before training.", lock: true },
  { k: "03", title: "Train a small open model", body: "Qwen3-4B, trained with veri.studio on the practice pages." },
  { k: "04", title: "Attacker round", body: "300 attacker-written pages added, half tricks, half honest. Trained again." },
  { k: "05", title: "Pick the best version", body: "Chosen on separate development pages, never on the test." },
  { k: "06", title: "Graded once", body: "The locked 300 pages, graded one time." },
] as const;

const clamp = (v: number) => Math.min(1, Math.max(0, v));

export function Pipeline({ progress }: { progress: MotionValue<number> | null }) {
  const [t, ref] = useDriver(progress, 9000, 1);
  // Stage i lights at i/N; the last 12% holds the finished pipeline.
  const span = 0.88;
  const pos = clamp(t / span) * STAGES.length;
  return (
    <div ref={ref} className="pl">
      <div className="pl-track" aria-hidden="true">
        <span className="pl-fill" style={{ transform: `scaleX(${clamp((pos - 0.5) / (STAGES.length - 1))})` }} />
        {Array.from({ length: 14 }, (_, i) => {
          const head = clamp((pos - 0.5) / (STAGES.length - 1));
          const x = ((i / 14 + t * 3) % 1) * head;
          return <i key={i} className="pl-dot" style={{ left: `${x * 100}%`, opacity: head > 0.02 ? 0.35 + 0.65 * ((i * 37) % 10) / 10 : 0 }} />;
        })}
      </div>
      <ol className="pl-stages">
        {STAGES.map((stage, i) => {
          const local = clamp(pos - i);
          const state = local >= 1 ? "done" : local > 0 ? "on" : "off";
          return (
            <li key={stage.k} className="pl-stage" data-state={state} style={{ ["--lit" as string]: local.toFixed(3) }}>
              <span className="pl-node" aria-hidden="true">
                <em>Station {stage.k}</em>
                <b>{"lock" in stage ? "LOCKED" : state === "done" ? "CLEARED" : state === "on" ? "IN PROGRESS" : "QUEUED"}</b>
              </span>
              <p className="pl-title">{stage.title}</p>
              <p className="pl-body">{stage.body}</p>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
