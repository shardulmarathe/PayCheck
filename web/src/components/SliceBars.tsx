import { SLICE_NAME, type SliceResult } from "../lib/results";

function pct(value: number): string {
  return `${Math.min(100, Math.max(0, value))}%`;
}

/**
 * Per-slice catch rates with a 95% confidence interval.
 * Rendered only for results that are not flagged synthetic.
 */
export function SliceBars({ slices }: { slices: SliceResult[] }) {
  if (slices.length === 0) return null;
  return (
    <div className="slice-split">
      {slices.map((slice) => (
        <section key={slice.id} className="slice-block" aria-hidden="true">
          <p className="label">{SLICE_NAME[slice.id]}</p>
          {slice.models.map((model) => {
            const low = model.ciLow;
            const high = model.ciHigh;
            const hasCi = low != null && high != null && high > low;
            return (
              <div key={model.id} className="slice-model">
                <span>{model.label}</span>
                <div className="slice-track">
                  {hasCi ? (
                    <i className="slice-ci" style={{ left: pct(low), width: pct(high - low) }} />
                  ) : null}
                  <i className={`slice-dot ${model.ours ? "ours" : ""}`} style={{ left: pct(model.score) }} />
                </div>
              </div>
            );
          })}
        </section>
      ))}
      <div className="sr-only">
        <table>
          <caption>Catch rate by slice, with 95% confidence intervals.</caption>
          <thead>
            <tr>
              <th>Slice</th>
              <th>Model</th>
              <th>Catch rate</th>
              <th>95% CI low</th>
              <th>95% CI high</th>
            </tr>
          </thead>
          <tbody>
            {slices.flatMap((slice) =>
              slice.models.map((model) => (
                <tr key={`${slice.id}-${model.id}`}>
                  <th>{SLICE_NAME[slice.id]}</th>
                  <td>{model.label}</td>
                  <td>{model.score}</td>
                  <td>{model.ciLow ?? "—"}</td>
                  <td>{model.ciHigh ?? "—"}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
