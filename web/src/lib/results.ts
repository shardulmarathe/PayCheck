import { trimNum } from "./format";

/** The three result slices. `in_dist` is familiar pages; the others are held out. */
export const SLICE_ORDER = ["in_dist", "heldout_attack", "heldout_template"] as const;

export type SliceId = (typeof SLICE_ORDER)[number];

export type Claim = "within" | "beats";

/** Spoken name of a slice. The hero tag is "on" plus this name. */
export const SLICE_NAME: Record<SliceId, string> = {
  in_dist: "familiar pages",
  heldout_attack: "new attacks",
  heldout_template: "new templates",
};

export interface SliceScore {
  id: string;
  label: string;
  score: number;
  ciLow: number | null;
  ciHigh: number | null;
  ours: boolean;
  sonnet: boolean;
}

export interface SliceResult {
  id: SliceId;
  claim: Claim;
  /** Absolute gap is spoken only for a "within" claim. Null keeps the literal [N]. */
  gapPoints: number | null;
  models: SliceScore[];
}

export interface ResultsView {
  /** Which slice the hero claims. Defaults to in_dist. */
  heroSlice: SliceId;
  /**
   * Sonnet cost_per_page_usd / ours. Null hides the cost phrase.
   * Never derived from cost_per_1k_checks_usd.
   */
  costRatio: number | null;
  /** Empty when the only results file is synthetic, so production draws no slice scores. */
  slices: SliceResult[];
}

export const EMPTY_RESULTS: ResultsView = {
  heroSlice: "in_dist",
  costRatio: null,
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

/**
 * "beats" is spoken only when the file says so AND the paired bootstrap 95% CI on
 * (guard − Sonnet) excludes 0 on the positive side. Read from `paired_ci95: [lo, hi]`
 * or `diff_ci_low` / `diff_ci_high`. Anything else downgrades to "within".
 */
function sliceClaim(cell: Record<string, unknown>): Claim {
  if (claimOf(cell.claim) !== "beats") return "within";
  const pair = Array.isArray(cell.paired_ci95) ? cell.paired_ci95 : [cell.diff_ci_low, cell.diff_ci_high];
  const lo = finite(pair[0]);
  const hi = finite(pair[1]);
  return lo != null && hi != null && Math.min(lo, hi) > 0 ? "beats" : "within";
}

function gapToken(gap: number | null): string {
  return gap == null ? "[N]" : trimNum(Math.abs(gap));
}

function withCost(sentence: string, costRatio: number | null): string {
  if (costRatio == null || !(costRatio > 0)) return sentence;
  return `${sentence} at 1/${trimNum(costRatio)} the cost`;
}

/** One slice, for the hero. Cost is appended only when the ratio came from data. */
export function heroClaim(results: ResultsView): { sentence: string; tag: string } {
  const id = isSliceId(results.heroSlice) ? results.heroSlice : "in_dist";
  const slice = results.slices.find((item) => item.id === id);
  const claim = slice?.claim === "beats" ? "beats" : "within";
  const body = claim === "beats" ? "Level with the baseline model" : `Within ${gapToken(slice?.gapPoints ?? null)} points of the baseline model`;
  return {
    sentence: `${withCost(body, results.costRatio)}.`,
    tag: sliceTag(id),
  };
}

/**
 * Benchmarks states every published slice. An empty list falls back to the
 * same non-overclaiming within-line the hero uses, with no cost phrase.
 */
export function benchmarksSonnetLine(results: ResultsView): string {
  if (results.slices.length === 0) return heroClaim({ ...EMPTY_RESULTS, heroSlice: results.heroSlice }).sentence;
  const parts = SLICE_ORDER.filter((id) => results.slices.some((slice) => slice.id === id)).map((id) => {
    const slice = results.slices.find((item) => item.id === id);
    if (!slice) return "";
    if (slice.claim === "beats") return `level with the baseline model on ${SLICE_NAME[id]}`;
    return `within ${gapToken(slice.gapPoints)} points on ${SLICE_NAME[id]}`;
  });
  const sentence = parts.filter(Boolean).join(", ");
  const capped = sentence.charAt(0).toUpperCase() + sentence.slice(1);
  const cost = results.costRatio != null && results.costRatio > 0 ? `, at 1/${trimNum(results.costRatio)} the cost` : "";
  return `${capped}${cost}.`;
}

/**
 * Gap-line label. Returns null when neither a page-cost ratio nor a numeric
 * point gap is present, so the chart does not invent "1/[N] the cost".
 */
export function gapLabel(costRatio: number | null, pointGap: number | null): string | null {
  const parts: string[] = [];
  if (costRatio != null && costRatio > 0) parts.push(`1/${trimNum(costRatio)} the cost`);
  if (pointGap != null && Number.isFinite(pointGap)) {
    const signed = pointGap > 0 ? `+${trimNum(pointGap)}` : pointGap < 0 ? `-${trimNum(Math.abs(pointGap))}` : "0";
    parts.push(`${signed} pts`);
  }
  return parts.length ? parts.join(" · ") : null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function oursId(id: string): boolean {
  return id === "guard" || id === "sureshop";
}

function sonnetId(id: string, label: string): boolean {
  return id === "sonnet" || id === "claude" || /sonnet/i.test(id) || /sonnet/i.test(label);
}

interface RawModel {
  label: string;
  cost: number | null;
}

function readModelMeta(raw: unknown): RawModel | undefined {
  if (!isRecord(raw)) return undefined;
  const label = typeof raw.label === "string" ? raw.label : "";
  return { label, cost: finite(raw.cost_per_page_usd) };
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
    sonnet: sonnetId(id, label),
  };
}

function rememberCost(catalog: Map<string, RawModel>, id: string, label: string, raw: unknown) {
  if (!isRecord(raw)) return;
  const cost = finite(raw.cost_per_page_usd);
  if (cost == null || !(cost > 0)) return;
  const prev = catalog.get(id);
  if (prev?.cost != null && prev.cost > 0) return;
  catalog.set(id, { label: prev?.label || label, cost });
}

function readScores(raw: unknown, catalog: Map<string, RawModel>): SliceScore[] {
  const scores: SliceScore[] = [];
  const take = (id: string, item: unknown) => {
    const score = readScore(id, item, catalog.get(id));
    if (!score) return;
    rememberCost(catalog, id, score.label, item);
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
  scores.sort((a, b) => Number(b.ours) - Number(a.ours) || Number(b.sonnet) - Number(a.sonnet) || a.label.localeCompare(b.label));
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
      models,
    });
  }
  if (slices.length === 0) return undefined;
  const heroRaw = typeof raw.hero_slice === "string" ? raw.hero_slice : "in_dist";
  const heroSlice: SliceId = isSliceId(heroRaw) ? heroRaw : "in_dist";
  const costFor = (ids: string[], pred: (id: string, label: string) => boolean): number | null => {
    for (const id of ids) {
      const cost = catalog.get(id)?.cost;
      if (cost != null && cost > 0) return cost;
    }
    for (const [id, meta] of catalog) {
      if (pred(id, meta.label) && meta.cost != null && meta.cost > 0) return meta.cost;
    }
    return null;
  };
  const oursCost = costFor(["guard", "sureshop"], (id) => oursId(id));
  const sonnetCost = costFor(["sonnet", "claude"], sonnetId);
  const costRatio = oursCost != null && sonnetCost != null ? sonnetCost / oursCost : null;
  if (synthetic) return { synthetic: true };
  return { synthetic: false, view: { heroSlice, costRatio, slices } };
}

/** Guards the spoken rules. Runs when the dataset module loads. */
export function assertClaimRules(): void {
  const hidden = heroClaim(EMPTY_RESULTS);
  if (hidden.sentence !== "Within [N] points of the baseline model.") {
    throw new Error(`hidden hero claim changed: ${hidden.sentence}`);
  }
  if (hidden.tag !== "on familiar pages") throw new Error(`hidden hero tag changed: ${hidden.tag}`);
  if (hidden.sentence.includes("1/") || hidden.sentence.toLowerCase().includes("sonnet-level")) {
    throw new Error("hidden hero claim hardcodes a cost or overclaims Sonnet");
  }
  const sample = normalizeResults({
    synthetic: false,
    hero_slice: "heldout_attack",
    models: {
      guard: { label: "SureShop guard", cost_per_page_usd: 0.00004 },
      sonnet: { label: "Baseline model", cost_per_page_usd: 0.0062 },
    },
    slices: {
      in_dist: {
        claim: "beats",
        gap_points: 2,
        paired_ci95: [0.4, 3.8],
        scores: {
          guard: { score: 93, ci_low: 89, ci_high: 96 },
          baseline: { score: null, ci_low: null, ci_high: null },
        },
      },
      heldout_attack: {
        claim: "within",
        gap_points: 5.5,
        scores: {
          guard: { score: 84, ci_low: 79, ci_high: 88 },
          baseline: { score: null, ci_low: null, ci_high: null },
        },
      },
      heldout_template: {
        claim: "within",
        gap_points: 3,
        scores: {
          guard: { score: 88, ci_low: 83, ci_high: 92 },
          baseline: { score: null, ci_low: null, ci_high: null },
        },
      },
    },
  });
  if (!sample || sample.synthetic) throw new Error("sample results did not parse");
  const attack = heroClaim(sample.view);
  if (attack.sentence !== "Within 5.5 points of the baseline model at 1/[N] the cost.") {
    throw new Error(`hero slice claim changed: ${attack.sentence}`);
  }
  if (attack.tag !== "on new attacks") throw new Error(`hero slice tag changed: ${attack.tag}`);
  const line = benchmarksSonnetLine(sample.view);
  if (line !== "Level with the baseline model on familiar pages, within 5.5 points on new attacks, within 3 points on new templates, at 1/[N] the cost.") {
    throw new Error(`benchmarks slice line changed: ${line}`);
  }
  const beatOnly = heroClaim({
    heroSlice: "in_dist",
    costRatio: null,
    slices: [{ id: "in_dist", claim: "beats", gapPoints: 2, models: [] }],
  });
  if (beatOnly.sentence !== "Level with the baseline model.") throw new Error(`beats claim changed: ${beatOnly.sentence}`);
  const noCi = normalizeResults({
    synthetic: false,
    slices: { heldout_template: { claim: "beats", gap_points: 2, paired_ci95: [-0.5, 4], scores: {} } },
  });
  if (!noCi || noCi.synthetic || noCi.view.slices[0]?.claim !== "within") {
    throw new Error("beats was spoken without a paired CI that excludes 0");
  }
  const mockShaped = normalizeResults({
    synthetic: true,
    hero_slice: "in_dist",
    slices: { in_dist: { claim: "beats", gap_points: 9, scores: { guard: { score: 99, ci_low: 98, ci_high: 100 } } } },
  });
  if (!mockShaped || !mockShaped.synthetic) throw new Error("synthetic flag was not honored");
  if (gapLabel(null, null) !== null) throw new Error("gap label invented a cost phrase");
}
