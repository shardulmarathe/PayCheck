import type { VisaTrace as VisaTraceData } from "../lib/types";

export function VisaSection({ traces }: { traces: VisaTraceData[] }) {
  if (traces.length === 0) return null;
  return (
    <div className="wrap">
      <section className="section" aria-labelledby="visa-title">
        <p className="label">Visa</p>
        <h1 id="visa-title" className="h1">
          Signed agent check (Visa Trusted Agent Protocol)
        </h1>
        {traces.map((trace) => (
          <ol key={trace.id} className="visa-trace">
            {trace.stages.map((stage) => (
              <li key={stage.key}>
                <h2 className="title">{stage.label}</h2>
                <pre>{stage.text}</pre>
              </li>
            ))}
          </ol>
        ))}
      </section>
    </div>
  );
}
