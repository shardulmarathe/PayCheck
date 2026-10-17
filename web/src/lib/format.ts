export function trimNum(n: number): string {
  if (!Number.isFinite(n)) return "—";
  const rounded = Math.round(n * 100) / 100;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(2).replace(/0$/, "").replace(/\.0$/, "");
}

export function formatUsd(n: number, digits = 2): string {
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatTally(n: number, format: "count" | "dollars"): string {
  if (format === "dollars") {
    return Number.isInteger(n) ? `$${n.toLocaleString("en-US")}` : formatUsd(n);
  }
  return n.toLocaleString("en-US");
}

export function formatMs(n: number): string {
  return `${Math.round(n).toLocaleString("en-US")} ms`;
}

export function formatPct(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return `${trimNum(n)}%`;
}

export function formatCost(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return formatUsd(n);
}

/** m:ss from milliseconds. */
export function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function roundLabel(round: number): string {
  return round === 0 ? "Base" : `Round ${round}`;
}
