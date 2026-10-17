import { CostScatter } from "../components/Charts";
import { ExampleMark } from "../components/Chrome";
import { HiddenTrick } from "../components/HiddenTrick";
import { SliceBars } from "../components/SliceBars";
import { HeldOutTable, SummaryTable } from "../components/Tables";
import { COPY } from "../lib/copy";
import { trimNum } from "../lib/format";
import { benchmarksSonnetLine, gapLabel } from "../lib/results";
import type { Dataset } from "../lib/types";

function token(value: number | null, placeholder: string): string {
  return value == null || !Number.isFinite(value) ? placeholder : trimNum(Math.abs(value));
}

export function Benchmarks({ data }: { data: Dataset }) {
  const bench = data.benchmarks;
  const headline = [COPY.catchLine(token(bench.catch_pct, "[X]")), benchmarksSonnetLine(data.results)] as const;
  const gap = gapLabel(data.results.costRatio, bench.point_gap);
  return (
    <div className="wrap">
      <section className="section">
        <p className="label">
          {bench.kicker}
          {data.example.eval ? " · example data" : ""}
        </p>
        <h1 className="h1 claim-title">
          <span data-catch-slot>{headline[0]}</span>
          <br />
          {headline[1]}
        </h1>
        <p className="body-l claim-body" style={{ marginTop: 20 }}>
          {bench.body}
        </p>
        <SliceBars slices={data.results.slices} />
      </section>
      <section className="section">
        <div className="kicker-row">
          <p className="label">Catch rate vs cost per 1,000 checks</p>
          <ExampleMark show={data.example.eval} />
        </div>
        <CostScatter models={data.models} gap={gap} costAxis={bench.cost_axis} />
        <HiddenTrick id="benchmarks-addon" kind="solid" label="Blocked · pre-checked add-on">
          <span className="trick-box" />
          Add extended analysis +$4.99
        </HiddenTrick>
      </section>
      <section className="section">
        <div className="kicker-row">
          <h2 className="held-title">On the two trick types it never trained on</h2>
          <ExampleMark show={data.example.eval} />
        </div>
        <HeldOutTable models={data.models} />
      </section>
      <SummaryTable
        models={data.models}
        kicker="Summary"
        title=""
        note={bench.summary_note}
        example={data.example.eval}
      />
    </div>
  );
}
