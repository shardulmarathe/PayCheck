export const SLICE_ORDER = ["in_dist", "heldout_attack", "heldout_template"] as const;

export type SliceId = (typeof SLICE_ORDER)[number];

export type Claim = "within" | "beats";

export const SLICE_NAME: Record<SliceId, string> = {
  in_dist: "in_dist",
  heldout_attack: "unseen trick types",
  heldout_template: "new layouts",
};

/** What a slice reports. Unseen trick types have no honest pages, so only tricks caught applies there. */
export type SliceMetric = "F1" | "catch";

export interface SliceScore {
  id: string;
  label: string;
  score: number;
  ciLow: number | null;
  ciHigh: number | null;
  ours: boolean;
  baseline: boolean;
  display: string | null;
}

export interface SliceResult {
  id: SliceId;
  claim: Claim;
  /** Kept for the file schema; no sentence is built from it. */
  gapPoints: number | null;
  metric: SliceMetric;
  models: SliceScore[];
}

export interface ResultsView {
  /** Which slice the hero claims. Defaults to in_dist. */
  heroSlice: SliceId;
  /** Empty when the only results file is synthetic, so production draws no slice scores. */
  slices: SliceResult[];
}

export const EMPTY_RESULTS: ResultsView = {
  heroSlice: "in_dist",
  slices: [],
};

export function sliceTag(id: SliceId): string {
  return `on ${SLICE_NAME[id]}`;
}

export function isSliceId(value: string): value is SliceId {
  return (SLICE_ORDER as readonly string[]).includes(value);
}

function claimOf(value: unknown): Claim {
  return value === "beats" ? "beats" : "within";
}

function finite(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function sliceClaim(cell: Record<string, unknown>): Claim {
  if (claimOf(cell.claim) !== "beats") return "within";
  const pair = Array.isArray(cell.paired_ci95) ? cell.paired_ci95 : [cell.diff_ci_low, cell.diff_ci_high];
  const lo = finite(pair[0]);
  const hi = finite(pair[1]);
  return lo != null && hi != null && Math.min(lo, hi) > 0 ? "beats" : "within";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function oursId(id: string): boolean {
  return id === "guard" || id === "sureshop";
}

function baselineId(id: string, label: string): boolean {
  return id === "baseline" || id === "claude" || /baseline/i.test(id) || /baseline/i.test(label);
}

interface RawModel {
  label: string;
}

function readModelMeta(raw: unknown): RawModel | undefined {
  if (!isRecord(raw)) return undefined;
  const label = typeof raw.label === "string" ? raw.label : "";
  return { label };
}

function readScore(id: string, raw: unknown, meta: RawModel | undefined): SliceScore | undefined {
  if (!isRecord(raw)) return undefined;
  const score = finite(raw.score);
  if (score == null) return undefined;
  const low = finite(raw.ci_low);
  const high = finite(raw.ci_high);
  const paired = low != null && high != null;
  const label = (typeof raw.label === "string" && raw.label) || meta?.label || id;
  return {
    id,
    label,
    score,
    ciLow: paired ? Math.min(low, high) : null,
    ciHigh: paired ? Math.max(low, high) : null,
    ours: oursId(id),
    baseline: baselineId(id, label),
    display: typeof raw.display === "string" ? raw.display : null,
  };
}

function readScores(raw: unknown, catalog: Map<string, RawModel>): SliceScore[] {
  const scores: SliceScore[] = [];
  const take = (id: string, item: unknown) => {
    const score = readScore(id, item, catalog.get(id));
    if (!score) return;
    scores.push(score);
  };
  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (!isRecord(item) || typeof item.id !== "string") continue;
      take(item.id, item);
    }
  } else if (isRecord(raw)) {
    for (const [id, item] of Object.entries(raw)) take(id, item);
  }
  scores.sort((a, b) => Number(b.ours) - Number(a.ours) || Number(b.baseline) - Number(a.baseline) || a.label.localeCompare(b.label));
  return scores;
}

export type NormalizedResults = { synthetic: true } | { synthetic: false; view: ResultsView };

/**
 * Parse a results file. `synthetic: true` is valid schema and must not be rendered.
 * Returns undefined when the file is not a results object.
 */
export function normalizeResults(raw: unknown): NormalizedResults | undefined {
  if (!isRecord(raw) || !isRecord(raw.slices)) return undefined;
  const synthetic = raw.synthetic === true;
  const catalog = new Map<string, RawModel>();
  if (isRecord(raw.models)) {
    for (const [id, meta] of Object.entries(raw.models)) {
      const parsed = readModelMeta(meta);
      if (parsed) catalog.set(id, parsed);
    }
  }
  const slices: SliceResult[] = [];
  for (const id of SLICE_ORDER) {
    const cell = raw.slices[id];
    if (!isRecord(cell)) continue;
    const models = readScores(cell.scores ?? cell.models, catalog);
    slices.push({
      id,
      claim: sliceClaim(cell),
      gapPoints: finite(cell.gap_points),
      metric: cell.metric === "catch" || id === "heldout_attack" ? "catch" : "F1",
      models,
    });
  }
  if (slices.length === 0) return undefined;
  const heroRaw = typeof raw.hero_slice === "string" ? raw.hero_slice : "in_dist";
  const heroSlice: SliceId = isSliceId(heroRaw) ? heroRaw : "in_dist";
  if (synthetic) return { synthetic: true };
  return { synthetic: false, view: { heroSlice, slices } };
}

/** Guards the parsing rules. Runs when the dataset module loads. */
export function assertClaimRules(): void {
  if (sliceTag("heldout_template") !== "on new layouts") throw new Error("slice name drifted from the pack");
  if (sliceTag("heldout_attack") !== "on unseen trick types") throw new Error("slice name drifted from the pack");
  const sample = normalizeResults({
    synthetic: false,
    slices: {
      in_dist: { metric: "F1", scores: { guard: { score: 0.805, ci_low: 0.733, ci_high: 0.868, display: "0.805 [0.733, 0.868]" } } },
      heldout_attack: { scores: { guard: { score: 0.219, ci_low: 0.094, ci_high: 0.375, display: "0.219" } } },
    },
  });
  if (!sample || sample.synthetic) throw new Error("sample results did not parse");
  if (sample.view.slices.find((slice) => slice.id === "heldout_attack")?.metric !== "catch") {
    throw new Error("unseen trick types must report tricks caught, not F1");
  }
  if (sample.view.slices[0]?.models[0]?.display !== "0.805 [0.733, 0.868]") throw new Error("display text was not kept verbatim");
  const noCi = normalizeResults({
    synthetic: false,
    slices: { heldout_template: { claim: "beats", gap_points: 2, paired_ci95: [-0.5, 4], scores: {} } },
  });
  if (!noCi || noCi.synthetic || noCi.view.slices[0]?.claim !== "within") {
    throw new Error("beats was accepted without a paired CI that excludes 0");
  }
  const mockShaped = normalizeResults({
    synthetic: true,
    hero_slice: "in_dist",
    slices: { in_dist: { claim: "beats", gap_points: 9, scores: { guard: { score: 99, ci_low: 98, ci_high: 100 } } } },
  });
  if (!mockShaped || !mockShaped.synthetic) throw new Error("synthetic flag was not honored");
}
