import { formatPct, formatUsd } from "../lib/format";
import type { BrowserUseResults } from "../lib/types";

function Rate({ label, value }: { label: string; value: number | null }) {
  if (value == null) return null;
  return (
    <div className="bu-rate">
      <p className="micro">{label}</p>
      <p className="bu-figure">{formatPct(value)}</p>
    </div>
  );
}

function Money({ label, value, loss }: { label: string; value: number | null; loss?: boolean }) {
  if (value == null) return null;
  return (
    <div className="bu-rate">
      <p className="micro">{label}</p>
      <p className={loss ? "bu-money loss-fill" : "bu-money"}>{formatUsd(value)}</p>
    </div>
  );
}

export function BrowserUse({ data }: { data: BrowserUseResults }) {
  if (data.runs.length === 0) return null;
  const paid = data.paid_for_trick.unguarded != null || data.paid_for_trick.guarded != null;
  const over = data.overpaid.unguarded != null || data.overpaid.guarded != null;
  return (
    <div className="wrap">
      <section className="section" aria-labelledby="browser-use-title">
        <p className="label">Browser Use</p>
        <h1 id="browser-use-title" className="h1">
          The same errands, with and without the guard.
        </h1>
        {paid ? (
          <div className="bu-block">
            <h2 className="title">Paid for the trick</h2>
            <div className="bu-pair">
              <Rate label="Unguarded" value={data.paid_for_trick.unguarded} />
              <Rate label="Guarded" value={data.paid_for_trick.guarded} />
            </div>
          </div>
        ) : null}
        {data.false_block_rate != null ? (
          <div className="bu-block">
            <h2 className="title">False blocks</h2>
            <div className="bu-pair">
              <Rate label="Guarded, clean pages" value={data.false_block_rate} />
            </div>
          </div>
        ) : null}
        {over ? (
          <div className="bu-block">
            <h2 className="title">Dollars overpaid</h2>
            <div className="bu-pair">
              <Money label="Unguarded" value={data.overpaid.unguarded} loss />
              <Money label="Guarded" value={data.overpaid.guarded} />
            </div>
          </div>
        ) : null}
        <ul className="bu-runs">
          {data.runs.map((run) => (
            <li key={run.id}>
              <p className="bu-run-title">
                {run.errand_id} · {run.mode}
              </p>
              <p className="bu-provenance">{run.provenance}</p>
              {run.video ? (
                <video className="bu-video" controls playsInline preload="metadata" src={run.video} />
              ) : null}
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
