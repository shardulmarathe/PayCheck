import { ExampleMark } from "../components/Chrome";
import { RequestBlock, ResponseBlock } from "../components/CodeBlock";
import { LoopDiagram } from "../components/Loop";
import { HELD_OUT, TRAINED_ON } from "../lib/taxonomy";
import type { Dataset, UpsellReplay } from "../lib/types";

export function DesignProcess({ data }: { data: Dataset }) {
  const process = data.process;
  const upsell = data.replays.find((replay): replay is UpsellReplay => replay.scene === "upsell");
  const stepsExample = data.example.training || data.example.eval;
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
        <div className="loop-band">
          <div>
            <p className="label">{process.sources_label}</p>
            {process.sources.map((source) => (
              <div key={source.title} className="source">
                <h3>{source.title}</h3>
                <p className="micro">{source.detail}</p>
              </div>
            ))}
            <div className="feeds">
              <span className="feeds-line" />
              <p className="micro">{process.feeds_label}</p>
            </div>
          </div>
          <LoopDiagram
            nodes={process.nodes}
            roundLabel={process.round_label}
            caught={process.caught_pct}
            caption={process.caught_caption}
            example={data.example.training}
          />
        </div>
      </section>
      <section className="section">
        <div className="kicker-row">
          <p className="label">{process.steps_kicker}</p>
          <ExampleMark show={stepsExample} />
        </div>
        <div className="steps">
          {process.steps.map((step) => (
            <article key={step.n} className="step">
              <p className="micro">{step.n}</p>
              <h3 className="title">{step.title}</h3>
              <p className="mono meta">{step.meta}</p>
              <p className="body">{step.body}</p>
              {step.n === "02" ? (
                <div className="tag-rows">
                  <p>
                    <span className="label">Trained on</span>
                    {TRAINED_ON.join(" · ")}
                  </p>
                  <p>
                    <span className="label">Held out of training</span>
                    {HELD_OUT.join(" · ")}
                  </p>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>
      <section className="section plug">
        <div>
          <p className="label">{process.plug_kicker}</p>
          <h2 className="h2">
            {process.plug_title_lines[0]}
            <br />
            {process.plug_title_lines[1]}
          </h2>
          <p className="body" style={{ marginTop: 16 }}>
            {process.plug_body}
          </p>
        </div>
        <div>
          <div className="kicker-row" style={{ marginBottom: 8 }}>
            <span />
            <ExampleMark show={data.example.replays} />
          </div>
          <RequestBlock label={process.request_label} code={process.request_code} />
          {upsell ? <ResponseBlock label={process.response_label} verdict={upsell.verdict} /> : null}
          <p className="micro endpoint-note">{process.endpoint_note}</p>
        </div>
      </section>
    </div>
  );
}
