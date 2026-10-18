// Dev-only preview for <ReplayStage />: open /replay-preview.html in `vite dev`.
// Not part of the production build (vite only builds index.html).
// Query: ?s=price|fake|tax  &t=<ms> freezes the clock (screenshots)  &advance=0 stops auto-advance.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MotionConfig } from "framer-motion";
import { ReplayStage } from "./components/replay/ReplayStage";
import { ShieldInterceptDemo } from "./components/replay/ShieldIntercept";
import type { ScenarioId } from "./components/replay/replayRuns";

const q = new URLSearchParams(window.location.search);
const s = q.get("s");
const scenario: ScenarioId = s === "fake" || s === "tax" ? s : "price";
const tRaw = q.get("t");
const frozenAt = tRaw !== null && tRaw !== "" && Number.isFinite(Number(tRaw)) ? Number(tRaw) : undefined;

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root");
createRoot(root).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      {q.get("view") === "shield" ? (
        <div style={{ maxWidth: 760, margin: "0 auto", display: "grid", gap: 20, fontFamily: "monospace", color: "#a3adb9", fontSize: 13 }}>
          {(["unguarded", "block", "pass"] as const).map((m) => (
            <div key={m} style={{ display: "grid", gap: 8 }}>
              <span>{m === "unguarded" ? "NO GUARD" : m === "block" ? "PAYCHECK · BLOCK" : "PAYCHECK · PASS"}</span>
              <ShieldInterceptDemo mode={m} frozenAt={frozenAt} amount={m === "pass" ? "$11.99" : "$12.49"} />
            </div>
          ))}
        </div>
      ) : (
        <ReplayStage initialScenario={scenario} frozenAt={frozenAt} autoAdvance={q.get("advance") !== "0"} />
      )}
    </MotionConfig>
  </StrictMode>,
);
