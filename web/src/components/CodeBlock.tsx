import { useState } from "react";
import type { Verdict } from "../lib/types";

export function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="copy-btn"
      aria-label={label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          window.setTimeout(() => setCopied(false), 1500);
        } catch {
          setCopied(false);
        }
      }}
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export function RequestBlock({ label, code }: { label: string; code: string }) {
  const [first, ...rest] = code.split("\n");
  return (
    <div className="code">
      <div className="code-bar">
        <p className="label">{label}</p>
        <CopyButton text={code} label={`Copy ${label}`} />
      </div>
      <pre>
        <span className="comment">{first}</span>
        {"\n"}
        {rest.join("\n")}
      </pre>
    </div>
  );
}

function verdictText(verdict: Verdict): string {
  const row = (key: string, value: string) => `  ${`${key}:`.padEnd(18)}${value}`;
  return `{
${row('"action"', `"${verdict.action}",`)}
${row('"latency_ms"', `${verdict.latency_ms},`)}
${row('"category"', `"${verdict.category}",`)}
${row('"trick"', `"${verdict.trick}",`)}
${row('"evidence"', `"${verdict.evidence}",`)}
${row('"steer"', `"${verdict.steer}",`)}
${row('"expected_total"', String(verdict.expected_total))}
}`;
}

export function ResponseBlock({ label, verdict }: { label: string; verdict: Verdict }) {
  const text = verdictText(verdict);
  const rows: { key: string; value: string; trick?: boolean }[] = [
    { key: "action", value: `"${verdict.action}",` },
    { key: "latency_ms", value: `${verdict.latency_ms},` },
    { key: "category", value: `"${verdict.category}",` },
    { key: "trick", value: `"${verdict.trick}",` },
    { key: "evidence", value: `"${verdict.evidence}",`, trick: true },
    { key: "steer", value: `"${verdict.steer}",` },
    { key: "expected_total", value: String(verdict.expected_total) },
  ];
  return (
    <div className="code">
      <div className="code-bar">
        <p className="label">{label}</p>
        <CopyButton text={text} label={`Copy ${label}`} />
      </div>
      <div className="code-body">
        {"{"}
        {rows.map((row) => (
          <div key={row.key}>
            {"  "}
            <span className="key">{`"${row.key}":`}</span>
            {"  "}
            <span className={row.trick ? "trick" : undefined}>{row.value}</span>
          </div>
        ))}
        {"}"}
      </div>
    </div>
  );
}
