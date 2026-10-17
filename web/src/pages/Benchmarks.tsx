import { useState } from "react";
import { CostScatter, LatencyChart, RoundCatchChart, TrainingChart, pointFor, type Slice } from "../components/Charts";
import { ExampleMark } from "../components/Chrome";
import { AttackTable, SummaryTable } from "../components/Tables";
import { Tally } from "../components/Tally";
import type { Dataset } from "../lib/types";

export function Benchmarks({ data }: { data: Dataset }) {
  const [slice, setSlice] = useState<Slice>("300");
  const bench = data.benchmarks;
  const missingOnSlice = slice === "100" && data.models.some((model) => pointFor(model, "100") == null);
  const caption = slice === "300"
    ? bench.hollow_caption
    : missingOnSlice
      ? "Filled points have a 100-page catch rate in this dataset. Models without one are left off until runs/ includes catch_rate_100."
      : "All five models on the 100-page slice.";
  return (
    <div className="wrap">
      <section className="section">
        <div className="kicker-row">
          <p className="label">{bench.kicker}</p>
          <ExampleMark show={data.example.eval} />
        </div>
        <h1 className="h1">
          {bench.title_lines[0]}
          <br />
          {bench.title_lines[1]}
        </h1>
        <p className="body-l" style={{ marginTop: 20 }}>
          {bench.body}
        </p>
        <div className="roster">
          {bench.roster.map((col) => (
            <div key={col.label}>
              <p className="micro">{col.label}</p>
              <h3 className={col.label === "Guard" ? "emphasis" : undefined}>{col.title}</h3>
              <p className="micro">{col.detail}</p>
            </div>
          ))}
        </div>
        <div className="chart-grid">
          <div>
            <div className="kicker-row">
              <p className="label">{bench.training_title}</p>
              <ExampleMark show={data.example.training} />
            </div>
            <TrainingChart rounds={data.rounds} seenLabel={bench.seen_legend} heldLabel={bench.heldout_legend} />
          </div>
          <div>
            <p className="label">{bench.latency_title}</p>
            <LatencyChart models={data.models} note={bench.latency_note} />
          </div>
        </div>
      </section>
      <section className="section">
        <div className="cost-head">
          <div className="cost-title">
            <p className="label">{bench.cost_kicker}</p>
            <h3 className="h3">{bench.cost_headline}</h3>
            {bench.cost_placeholder ? <p className="micro caption">{bench.cost_note}</p> : null}
          </div>
          <div>
            <ExampleMark show={data.example.eval} />
            <div className="segment" role="radiogroup" aria-label="Test set slice" style={{ marginTop: 8 }}>
              <button type="button" role="radio" aria-checked={slice === "100"} onClick={() => setSlice("100")}>
                100-page slice
              </button>
              <button type="button" role="radio" aria-checked={slice === "300"} onClick={() => setSlice("300")}>
                All {bench.test_pages} pages
              </button>
            </div>
          </div>
        </div>
        <CostScatter models={data.models} slice={slice} annotation={bench.cost_annotation} />
        <p className="micro caption">{bench.cost_axis}</p>
        <p className="micro caption">{caption}</p>
        <div className="round-catch">
          <div className="kicker-row">
            <p className="label">Catch rate by round</p>
            <ExampleMark show={data.example.training} />
          </div>
          <RoundCatchChart rounds={data.rounds} />
        </div>
      </section>
      <SummaryTable
        models={data.models}
        kicker={bench.summary_kicker}
        title={bench.summary_title}
        note={bench.summary_note}
        example={data.example.eval}
      />
      <AttackTable
        models={data.models}
        kicker={bench.attack_kicker}
        title={bench.attack_title}
        caption={bench.attack_caption}
        example={data.example.eval}
      />
      <Tally kicker={data.tally.kicker} items={data.tally.items} example={data.example.tally} compact />
    </div>
  );
}
