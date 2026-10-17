import { ExampleMark } from "../components/Chrome";
import { HiddenTrick } from "../components/HiddenTrick";
import { LoopDiagram } from "../components/Loop";
import type { Dataset } from "../lib/types";

export function DesignProcess({ data }: { data: Dataset }) {
  const process = data.process;
  return (
    <div className="wrap">
      <section className="section">
        <p className="label">{process.kicker}</p>
        <h1 className="h1">
          {process.title_lines[0]}
          <br />
          {process.title_lines[1]}
        </h1>
        <p className="body-l" style={{ marginTop: 20 }}>
          {process.body}
        </p>
        <LoopDiagram
          nodes={process.nodes}
          roundLabel={process.round_label}
          caught={process.caught_pct}
          caption={process.caught_caption}
          example={data.example.training}
        />
      </section>
      <section className="section">
        <div className="kicker-row">
          <p className="label">{process.steps_kicker}</p>
          <ExampleMark show={data.example.training || data.example.eval} />
        </div>
        <div className="steps-v3">
          {process.steps.map((step) => (
            <article key={step.n} className="step-v3">
              <p className="micro">{step.n}</p>
              <div>
                <h3>{step.title}</h3>
                <p className="body">{step.body}</p>
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="section plug-v3">
        <div>
          <h2 className="h2">
            {process.plug_title_lines[0]}
            <br />
            {process.plug_title_lines[1]}
          </h2>
          <HiddenTrick id="design-urgency" kind="dashed" label="Blocked · fake urgency">
            <span className="trick-badge">Only 2 left!</span>
          </HiddenTrick>
        </div>
        <div className="code-card">
          <p className="label">TypeScript</p>
          <pre>{process.request_code}</pre>
        </div>
      </section>
    </div>
  );
}
