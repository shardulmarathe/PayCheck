import { Fragment, useState } from "react";
import { formatCost, formatLatency, formatMs, formatPct } from "../lib/format";
import { ATTACK_ROWS, METRICS, type MetricId } from "../lib/taxonomy";
import type { ModelEval } from "../lib/types";
import { ExampleMark } from "./Chrome";

const TABLE_ORDER = ["guard", "gemini", "claude", "qwen-base", "qwenguard"];

function ordered(models: ModelEval[]): ModelEval[] {
  return [...models].sort((a, b) => {
    const ai = TABLE_ORDER.indexOf(a.id);
    const bi = TABLE_ORDER.indexOf(b.id);
    if (ai === -1 && bi === -1) return 0;
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

function cell(model: ModelEval, rowId: string, metric: MetricId): number | null {
  if (metric === "catch_rate") return model.catch_rate_by_attack[rowId] ?? null;
  const specific = model.by_attack?.[rowId]?.[metric];
  if (specific != null) return specific;
  if (metric === "latency_ms") return model.latency_ms_median;
  if (metric === "cost_per_1k_checks_usd") return model.cost_per_1k_checks_usd;
  return null;
}

function formatCell(metric: MetricId, value: number | null): string {
  if (value == null) return "—";
  if (metric === "latency_ms") return formatMs(value);
  if (metric === "cost_per_1k_checks_usd") return formatCost(value);
  return formatPct(value);
}

function FamilyMark({ dashed }: { dashed: boolean }) {
  return (
    <svg className="family-mark" viewBox="0 0 12 12" aria-hidden="true">
      <path d="M8 1 H1 V8" fill="none" stroke="#9AA3AE" strokeWidth="1.5" strokeDasharray={dashed ? "2 1.5" : undefined} />
    </svg>
  );
}

export function SummaryTable({
  models,
  kicker,
  title,
  note,
  example,
}: {
  models: ModelEval[];
  kicker: string;
  title: string;
  note: string;
  example: boolean;
}) {
  const rows = ordered(models);
  return (
    <section className="section">
      <div className="kicker-row">
        <div>
          <p className="label">{kicker}</p>
          {title ? <h3 className="h3">{title}</h3> : null}
        </div>
        <ExampleMark show={example} />
      </div>
      <div className="table-scroll">
        <table className="data">
          <caption className="sr-only">Summary metrics per model</caption>
          <thead>
            <tr>
              <th>Model</th>
              <th>Catch rate</th>
              <th>False blocks</th>
              <th>Evidence match</th>
              <th>Median latency</th>
              <th>Cost per 1,000</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((model) => (
              <tr key={model.id}>
                <th scope="row">
                  {model.short}
                  {model.pages < 300 ? <span className="micro held">100 pages</span> : null}
                </th>
                <td className={model.emphasis ? "on" : undefined}>{formatPct(model.catch_rate)}</td>
                <td>{formatPct(model.false_block_rate)}</td>
                <td>{formatPct(model.evidence_match)}</td>
                <td>{formatLatency(model.latency_ms_median, example)}</td>
                <td>{formatCost(model.cost_per_1k_checks_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="micro caption">{note}</p>
    </section>
  );
}

const NOTES: Record<MetricId, string> = {
  catch_rate: "",
  false_block_rate: "False blocks are not broken out by attack in this dataset. Model-level rates are in the summary.",
  evidence_match: "Evidence match is not broken out by attack in this dataset. Model-level rates are in the summary.",
  latency_ms: "Median latency is per check. Each row repeats the model median until a per-attack series is in the data.",
  cost_per_1k_checks_usd: "Cost is per 1,000 checks. Each row repeats the model cost until a per-attack series is in the data.",
};

const HELD_OUT_MODELS = ["guard", "gemini", "claude"] as const;

export function HeldOutTable({ models }: { models: ModelEval[] }) {
  const columns = HELD_OUT_MODELS.map((id) => models.find((model) => model.id === id)).filter((model): model is ModelEval => !!model);
  const rows = ATTACK_ROWS.filter((row) => row.heldOut);
  return (
    <div className="table-scroll">
      <table className="data held-table">
        <caption className="sr-only">Catch rate on trick types held out of training</caption>
        <thead>
          <tr>
            <th>Trick</th>
            {columns.map((model) => (
              <th key={model.id} className={model.emphasis ? "on" : undefined}>
                {model.short}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <th scope="row">{row.label}</th>
              {columns.map((model) => (
                <td key={model.id} className={model.emphasis ? "on" : undefined}>
                  {formatPct(model.catch_rate_by_attack[row.id])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AttackTable({
  models,
  kicker,
  title,
  caption,
  example,
}: {
  models: ModelEval[];
  kicker: string;
  title: string;
  caption: string;
  example: boolean;
}) {
  const [metric, setMetric] = useState<MetricId>("catch_rate");
  const rows = ordered(models);
  const guard = rows.find((model) => model.emphasis);
  let lastFamily = "";
  return (
    <section className="section">
      <div className="section-head">
        <div>
          <p className="label">{kicker}</p>
          <h3 className="h3">{title}</h3>
        </div>
        <ExampleMark show={example} />
      </div>
      <div className="metric-toggle" role="radiogroup" aria-label="Metric">
        {METRICS.map((item) => (
          <button key={item.id} type="button" role="radio" aria-checked={metric === item.id} onClick={() => setMetric(item.id)}>
            {item.label}
          </button>
        ))}
      </div>
      <div className="table-scroll">
        <table className="data">
          <caption className="sr-only">{title}</caption>
          <thead>
            <tr>
              <th>Attack</th>
              {rows.map((model) => (
                <th key={model.id} className={model.emphasis ? "on" : undefined}>
                  {model.short}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ATTACK_ROWS.map((attack) => {
              const group = attack.family !== lastFamily;
              lastFamily = attack.family;
              const guardValue = guard ? cell(guard, attack.id, metric) : null;
              const showBar = metric === "catch_rate" || metric === "evidence_match" || metric === "false_block_rate";
              return (
                <Fragment key={attack.id}>
                  {group ? (
                    <tr className="group">
                      <th colSpan={rows.length + 1}>
                        <FamilyMark dashed={attack.family === "scam"} />
                        {attack.family === "upsell" ? "Upsell traps · solid bracket" : "Scams · dashed bracket"}
                      </th>
                    </tr>
                  ) : null}
                  <tr>
                    <th scope="row">
                      <span className="attack-name">
                        <span>
                          {attack.label}
                          {attack.heldOut ? <span className="micro held">Held out</span> : null}
                        </span>
                        {showBar && guardValue != null ? (
                          <span className="attack-bar" aria-hidden="true">
                            <i style={{ width: `${Math.max(0, Math.min(100, guardValue))}%` }} />
                          </span>
                        ) : null}
                      </span>
                    </th>
                    {rows.map((model) => {
                      const value = cell(model, attack.id, metric);
                      return (
                        <td key={model.id} className={model.emphasis ? "on" : undefined}>
                          {formatCell(metric, value)}
                        </td>
                      );
                    })}
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="micro caption">{metric === "catch_rate" ? caption : NOTES[metric]}</p>
    </section>
  );
}
