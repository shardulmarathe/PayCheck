import { CostScatter } from "../components/Charts";
import { ExampleMark } from "../components/Chrome";
import { HeldOutTable, SummaryTable } from "../components/Tables";
import { COPY } from "../lib/copy";
import type { Dataset } from "../lib/types";

export function Benchmarks({ data }: { data: Dataset }) {
  const bench = data.benchmarks;
  const clamped = data.models.filter((model) => model.catch_rate < 40);
  return (
    <div className="wrap">
      <section className="section">
        <p className="label">
          {bench.kicker}
          {data.example.eval ? " · example data" : ""}
        </p>
        <h1 className="h1">
          {COPY.benchmarksHeadline[0]}
          <br />
          {COPY.benchmarksHeadline[1]}
        </h1>
        <p className="body-l" style={{ marginTop: 20 }}>
          {bench.body}
        </p>
      </section>
      <section className="section">
        <div className="kicker-row">
          <p className="label">Catch rate vs cost per 1,000 checks</p>
          <ExampleMark show={data.example.eval} />
        </div>
        <CostScatter models={data.models} annotation={bench.cost_annotation} />
        <p className="micro caption">{bench.cost_axis}</p>
        {clamped.length ? (
          <p className="micro caption">
            {clamped.map((model) => `${model.model} · ${model.catch_rate}%`).join("; ")} {clamped.length === 1 ? "is" : "are"} below 40% and
            {clamped.length === 1 ? " sits" : " sit"} on the axis.
          </p>
        ) : null}
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
