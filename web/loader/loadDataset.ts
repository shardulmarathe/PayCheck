import fs from "node:fs";
import path from "node:path";
import { formatLatency, lostCounterCopy, subscriptionCopy, trimNum } from "../src/lib/format";
import { lossWindow, visualAt } from "../src/lib/replay";
import type {
  Dataset,
  ModelEval,
  Replay,
  TallyItem,
  TrainingRound,
  Verdict,
} from "../src/lib/types";
import { fixtureDataset } from "./fixtures";
import { assertClaimRules, EMPTY_RESULTS, normalizeResults, type ResultsView } from "../src/lib/results";

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

/** Build-time. Unset follows NODE_ENV: production hides examples, dev shows them with labels. */
export function showExamples(): boolean {
  const raw = process.env.NEXT_PUBLIC_SHOW_EXAMPLES?.trim().toLowerCase();
  if (raw === "1" || raw === "true" || raw === "yes") return true;
  if (raw === "0" || raw === "false" || raw === "no") return false;
  return process.env.NODE_ENV !== "production";
}

/** A runs file is publishable only when it explicitly says `"synthetic": false`. */
function publishable(raw: unknown): raw is Record<string, unknown> {
  return isRecord(raw) && raw.synthetic === false;
}

function readJson(file: string, notes: string[]): unknown | undefined {
  if (!fs.existsSync(file)) return undefined;
  try {
    return JSON.parse(fs.readFileSync(file, "utf8")) as unknown;
  } catch (error) {
    notes.push(`Could not parse ${file}: ${error instanceof Error ? error.message : String(error)}`);
    return undefined;
  }
}

function listJson(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((name) => name.endsWith(".json"))
    .sort()
    .map((name) => path.join(dir, name));
}

function numMap(value: unknown): Record<string, number> | undefined {
  if (!isRecord(value)) return undefined;
  const out: Record<string, number> = {};
  for (const [key, cell] of Object.entries(value)) {
    const n = num(cell);
    if (n != null) out[key] = n;
  }
  return out;
}

function normalizeModel(raw: unknown, notes: string[], file: string): ModelEval | undefined {
  if (!isRecord(raw)) {
    notes.push(`${file} is not a model object`);
    return undefined;
  }
  const id = str(raw.id);
  const model = str(raw.model);
  const catchRate = num(raw.catch_rate);
  const latency = num(raw.latency_ms_median);
  const cost = num(raw.cost_per_1k_checks_usd);
  if (!id || !model || catchRate == null || latency == null || cost == null) {
    notes.push(`${file} is missing id, model, catch_rate, latency_ms_median, or cost_per_1k_checks_usd`);
    return undefined;
  }
  const pages = num(raw.pages) ?? 300;
  const ciLow = num(raw.ci_low);
  const ciHigh = num(raw.ci_high);
  const ci = ciLow != null && ciHigh != null ? { low: ciLow, high: ciHigh } : null;
  const catch300 =
    raw.catch_rate_300 === null ? null : (num(raw.catch_rate_300) ?? (pages >= 300 ? catchRate : null));
  const catch100 =
    raw.catch_rate_100 === null ? null : (num(raw.catch_rate_100) ?? (pages <= 100 ? catchRate : null));
  const byAttackRaw = isRecord(raw.by_attack) ? raw.by_attack : undefined;
  let byAttack: ModelEval["by_attack"];
  if (byAttackRaw) {
    byAttack = {};
    for (const [row, cell] of Object.entries(byAttackRaw)) {
      if (!isRecord(cell)) continue;
      byAttack[row] = {
        catch_rate: cell.catch_rate === null ? null : num(cell.catch_rate),
        false_block_rate: cell.false_block_rate === null ? null : num(cell.false_block_rate),
        evidence_match: cell.evidence_match === null ? null : num(cell.evidence_match),
        latency_ms: cell.latency_ms === null ? null : num(cell.latency_ms),
        cost_per_1k_checks_usd: cell.cost_per_1k_checks_usd === null ? null : num(cell.cost_per_1k_checks_usd),
      };
    }
  }
  return {
    id,
    model,
    short: str(raw.short) ?? model,
    emphasis: raw.emphasis === true || raw.role === "guard",
    pages,
    catch_rate: catchRate,
    catch_rate_300: catch300,
    catch_rate_100: catch100,
    false_block_rate: raw.false_block_rate === null ? null : (num(raw.false_block_rate) ?? null),
    evidence_match: raw.evidence_match === null ? null : (num(raw.evidence_match) ?? null),
    latency_ms_median: latency,
    cost_per_1k_checks_usd: cost,
    ci_low: ci?.low ?? null,
    ci_high: ci?.high ?? null,
    catch_rate_by_attack: numMap(raw.catch_rate_by_attack) ?? {},
    by_attack: byAttack,
  };
}

function loadModels(runsRoot: string, notes: string[]): { models: ModelEval[]; claim?: "within" | "beats"; catch_pct: number | null; cost_ratio: number | null; point_gap: number | null } | "withheld" | undefined {
  const evalDir = path.join(runsRoot, "eval");
  const leaderboardPath = path.join(evalDir, "leaderboard.json");
  const leaderboard = readJson(leaderboardPath, notes);
  if (leaderboard != null && !publishable(leaderboard)) {
    notes.push("runs/eval/leaderboard.json is synthetic; benchmark scores stay hidden");
    return "withheld";
  }
  const rawModels: unknown[] = [];
  let claim: "within" | "beats" | undefined;
  let catchPct: number | null = null;
  let costRatio: number | null = null;
  let pointGap: number | null = null;
  if (publishable(leaderboard) && Array.isArray(leaderboard.models)) {
    rawModels.push(...leaderboard.models);
    if (leaderboard.claim === "beats" || leaderboard.claim === "within") claim = leaderboard.claim;
    catchPct = num(leaderboard.catch_pct) ?? null;
    costRatio = num(leaderboard.cost_ratio) ?? null;
    pointGap = num(leaderboard.point_gap) ?? null;
  } else if (Array.isArray(leaderboard)) {
    rawModels.push(...leaderboard);
  }
  if (rawModels.length === 0 && leaderboard == null) {
    let withheld = false;
    for (const file of listJson(evalDir)) {
      if (path.basename(file) === "leaderboard.json" || path.basename(file) === "results.json") continue;
      const parsed = readJson(file, notes);
      if (parsed == null) continue;
      if (!publishable(parsed)) {
        notes.push(`${path.basename(file)} is synthetic; benchmark scores stay hidden`);
        withheld = true;
        continue;
      }
      if (Array.isArray(parsed.models)) rawModels.push(...parsed.models);
      else rawModels.push(parsed);
    }
    if (rawModels.length === 0 && withheld) return "withheld";
  }
  if (rawModels.length === 0) return undefined;
  const models = rawModels
    .map((raw, index) => normalizeModel(raw, notes, `eval model ${index}`))
    .filter((model): model is ModelEval => !!model);
  return models.length ? { models, claim, catch_pct: catchPct, cost_ratio: costRatio, point_gap: pointGap } : undefined;
}

function normalizeRound(raw: unknown): TrainingRound | undefined {
  if (!isRecord(raw)) return undefined;
  const round = num(raw.round);
  const seen = num(raw.catch_seen);
  const held = num(raw.catch_heldout);
  if (round == null || seen == null || held == null) return undefined;
  return { round, catch_seen: seen, catch_heldout: held };
}

function takeRounds(items: unknown[], notes: string[], file: string): TrainingRound[] {
  const rounds: TrainingRound[] = [];
  for (const item of items) {
    const round = normalizeRound(item);
    if (round) rounds.push(round);
    else if (item) notes.push(`${file} is not a training round`);
  }
  rounds.sort((a, b) => a.round - b.round);
  return rounds;
}

function loadRounds(runsRoot: string, notes: string[]): TrainingRound[] | "withheld" | undefined {
  const trainingFiles = listJson(path.join(runsRoot, "training"));
  const fromFiles: TrainingRound[] = [];
  let withheld = false;
  for (const file of trainingFiles) {
    const parsed = readJson(file, notes);
    if (parsed == null) continue;
    if (!publishable(parsed)) {
      notes.push(`${path.basename(file)} is synthetic; training rounds stay hidden`);
      withheld = true;
      continue;
    }
    const items = Array.isArray(parsed.rounds) ? parsed.rounds : [parsed];
    fromFiles.push(...takeRounds(items, notes, path.basename(file)));
  }
  if (fromFiles.length) {
    fromFiles.sort((a, b) => a.round - b.round);
    return fromFiles;
  }
  if (trainingFiles.length) return withheld ? "withheld" : undefined;

  const fromEval: TrainingRound[] = [];
  for (const file of listJson(path.join(runsRoot, "eval"))) {
    const parsed = readJson(file, notes);
    if (!publishable(parsed) || !Array.isArray(parsed.rounds)) {
      if (parsed != null && isRecord(parsed) && Array.isArray(parsed.rounds)) {
        notes.push(`${path.basename(file)} rounds are synthetic; training rounds stay hidden`);
        withheld = true;
      }
      continue;
    }
    fromEval.push(...takeRounds(parsed.rounds, notes, path.basename(file)));
  }
  if (fromEval.length) {
    fromEval.sort((a, b) => a.round - b.round);
    return fromEval;
  }
  return withheld ? "withheld" : undefined;
}

function isVerdict(value: unknown): value is Verdict {
  if (!isRecord(value)) return false;
  return (
    (value.action === "allow" || value.action === "block") &&
    (value.latency_ms == null || num(value.latency_ms) != null) &&
    !!str(value.category) &&
    !!str(value.trick) &&
    !!str(value.evidence) &&
    !!str(value.steer) &&
    num(value.expected_total) != null &&
    !!str(value.readout)
  );
}

function isReplay(value: Record<string, unknown>): boolean {
  if (!isRecord(value) || !str(value.id) || !str(value.title) || !Array.isArray(value.steps)) return false;
  if (!isVerdict(value.verdict) || num(value.duration_ms) == null || num(value.budget) == null) return false;
  if (!isRecord(value.scene_view) || (value.scene_view.kind !== "cart" && value.scene_view.kind !== "scam")) {
    return false;
  }
  if (value.scene === "upsell") return isRecord(value.without) && isRecord(value.with);
  if (value.scene === "scam") return isRecord(value.columns);
  return false;
}

function moneyFields(value: Record<string, unknown>): Pick<Replay, "overcharge_usd" | "exposed" | "subscription" | "subscription_monthly_usd" | "synthetic"> {
  const cart = isRecord(value.final_cart) ? value.final_cart : undefined;
  const monthly = value.subscription_monthly_usd === null ? null : (num(value.subscription_monthly_usd) ?? null);
  return {
    overcharge_usd: num(value.overcharge_usd) ?? num(value.dollars_lost) ?? 0,
    exposed: value.exposed === true,
    subscription: value.subscription === true || value.unwanted_subscription === true || cart?.subscription === true,
    subscription_monthly_usd: monthly,
    synthetic: value.synthetic === true,
  };
}

function normalizeReplay(value: unknown): Replay | undefined {
  if (!isRecord(value) || !isReplay(value)) return undefined;
  return { ...(value as unknown as Replay), ...moneyFields(value) };
}

function loadReplays(runsRoot: string, notes: string[]): Replay[] | "withheld" | undefined {
  const files = listJson(path.join(runsRoot, "replays"));
  if (!files.length) return undefined;
  const replays: Replay[] = [];
  let withheld = false;
  for (const file of files) {
    const parsed = readJson(file, notes);
    if (parsed == null) continue;
    if (!publishable(parsed)) {
      notes.push(`${path.basename(file)} is synthetic; replays stay hidden`);
      withheld = true;
      continue;
    }
    const items = Array.isArray(parsed.replays) ? parsed.replays : [parsed];
    for (const item of items) {
      const replay = normalizeReplay(item);
      if (replay) replays.push({ ...replay, synthetic: false });
      else notes.push(`${path.basename(file)} is not a visual replay`);
    }
  }
  if (replays.length) return replays;
  return withheld ? "withheld" : undefined;
}

function isTallyItem(value: unknown): value is TallyItem {
  if (!isRecord(value)) return false;
  return (
    !!str(value.id) &&
    !!str(value.label) &&
    num(value.with_guard) != null &&
    num(value.without_guard) != null &&
    (value.format === "count" || value.format === "dollars") &&
    !!str(value.note) &&
    (value.from_tone === "loss" || value.from_tone === "muted")
  );
}

function loadTally(runsRoot: string, notes: string[]): TallyItem[] | "withheld" | undefined {
  const file = path.join(runsRoot, "tally.json");
  if (!fs.existsSync(file)) return undefined;
  const parsed = readJson(file, notes);
  if (parsed == null) return undefined;
  if (!publishable(parsed)) {
    notes.push("runs/tally.json is synthetic; tally stays hidden");
    return "withheld";
  }
  const items = Array.isArray(parsed.items) ? parsed.items : [parsed];
  const tally = items.filter(isTallyItem);
  if (tally.length !== items.length) notes.push("runs/tally.json has items that do not match the tally shape");
  return tally.length ? tally : undefined;
}

function applyDerived(ds: Dataset): Dataset {
  const rounds = [...ds.rounds].sort((a, b) => a.round - b.round);
  const last = rounds[rounds.length - 1];
  const trained = rounds.filter((round) => round.round > 0);
  const guard = ds.models.find((model) => model.emphasis) ?? ds.models[0];
  const upsell = ds.replays.find((replay) => replay.scene === "upsell");

  if (last) {
    ds.process.round_label = last.round === 0 ? "Base" : `Round ${last.round}`;
    ds.process.caught_pct = last.catch_seen;
  }
  const step04 = ds.process.steps.find((step) => step.n === "04");
  const step05 = ds.process.steps.find((step) => step.n === "05");
  if (step04 && guard && !ds.example.eval && guard.latency_ms_median != null) {
    step04.meta = `${formatLatency(guard.latency_ms_median)} median`;
  }
  if (step05 && !ds.example.training) step05.meta = `${trained.length} rounds so far`;
  if (guard && !ds.example.eval && guard.latency_ms_median != null) ds.hero.median_catch_ms = guard.latency_ms_median;
  else if (upsell && !ds.example.replays && upsell.verdict.latency_ms != null) {
    ds.hero.median_catch_ms = upsell.verdict.latency_ms;
  }

  const testPages = ds.models.some((model) => model.pages >= 300) ? 300 : (guard?.pages ?? ds.benchmarks.test_pages);
  ds.benchmarks.test_pages = testPages;
  const testSet = ds.benchmarks.roster.find((col) => col.label === "Test set");
  if (testSet) testSet.title = `${testPages} pages`;

  const claude = ds.models.find((model) => model.id === "claude" || /claude/i.test(model.model));
  if (!ds.example.eval && guard && claude && guard.cost_per_1k_checks_usd > 0) {
    if (ds.benchmarks.catch_pct == null) ds.benchmarks.catch_pct = guard.catch_rate;
    if (ds.benchmarks.cost_ratio == null) ds.benchmarks.cost_ratio = claude.cost_per_1k_checks_usd / guard.cost_per_1k_checks_usd;
    if (ds.benchmarks.point_gap == null) ds.benchmarks.point_gap = guard.catch_rate - claude.catch_rate;
    const ratio = ds.benchmarks.cost_ratio;
    const gap = ds.benchmarks.point_gap;
    if (ratio != null && gap != null) {
      const signed = `${gap > 0 ? "+" : gap < 0 ? "-" : ""}${trimNum(Math.abs(gap))}`;
      ds.benchmarks.cost_annotation = `1/${trimNum(ratio)} the cost · ${signed} pts`;
      ds.benchmarks.cost_placeholder = false;
    }
  }
  return ds;
}

/**
 * Real slice scores come from runs/eval/results.json (or runs/results.json).
 * The checked-in mock is synthetic, so its scores, claims, gaps, and costs stay hidden.
 */
function loadResults(repoRoot: string, notes: string[]): ResultsView {
  const mockPath = path.join(repoRoot, "web", "loader", "results.mock.json");
  const mock = normalizeResults(readJson(mockPath, notes));
  if (!mock?.synthetic) {
    throw new Error("web/loader/results.mock.json must stay a synthetic results file");
  }

  const candidates = [path.join(repoRoot, "runs", "eval", "results.json"), path.join(repoRoot, "runs", "results.json")];
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    const parsed = normalizeResults(readJson(file, notes));
    const label = path.relative(repoRoot, file);
    if (!parsed) {
      notes.push(`${label} is not a results file`);
      continue;
    }
    if (parsed.synthetic) {
      notes.push(`${label} is synthetic; slice scores stay hidden`);
      return EMPTY_RESULTS;
    }
    notes.push(`results from ${label}`);
    return parsed.view;
  }
  notes.push("results.mock.json is synthetic; slice scores stay hidden");
  return EMPTY_RESULTS;
}

function assertDefaultReplay(): void {
  const upsell = fixtureDataset.replays.find((replay) => replay.scene === "upsell");
  if (!upsell || upsell.scene !== "upsell") throw new Error("default replay missing");
  const window = lossWindow(upsell);
  if (window.end > 20_000) throw new Error("default replay loss window passes 20s");
  const atTwenty = visualAt(20_000, upsell, false);
  if (atTwenty.loss < 1) throw new Error(`default replay loss is ${atTwenty.loss} at 20s`);
  if (upsell.overcharge_usd !== 9.99 || upsell.exposed || upsell.subscription || upsell.subscription_monthly_usd != null) {
    throw new Error("default replay money fields drifted");
  }
  if (lostCounterCopy(upsell.overcharge_usd) !== "lost $9.99") {
    throw new Error(`lost counter copy was ${lostCounterCopy(upsell.overcharge_usd)}`);
  }
  if (subscriptionCopy(14.99) !== "Signed you up for $14.99/month") {
    throw new Error(`subscription copy was ${subscriptionCopy(14.99)}`);
  }
}

function hideSynthetic(ds: Dataset, show: boolean, real: { models: boolean; rounds: boolean; replays: boolean; tally: boolean }): void {
  const resultsReal = ds.results.slices.length > 0;
  ds.shown = {
    benchmarks: show || real.models || resultsReal,
    replays: show || real.replays,
    training: show || real.rounds,
    tally: show || real.tally,
  };
  if (!ds.shown.benchmarks || (!show && !real.models)) {
    if (!real.models) ds.models = [];
    if (!ds.shown.benchmarks) {
      ds.benchmarks.catch_pct = null;
      ds.benchmarks.cost_ratio = null;
      ds.benchmarks.point_gap = null;
      ds.benchmarks.cost_annotation = "";
      ds.results = EMPTY_RESULTS;
    }
  }
  if (!ds.shown.replays) ds.replays = [];
  if (!ds.shown.training) {
    ds.rounds = [];
    ds.process.caught_pct = null;
    ds.process.round_label = "";
  }
  if (!ds.shown.tally) ds.tally.items = [];
}

/** Build-time dataset. Real runs/ JSON replaces a section; synthetic sections are omitted unless examples are on. */
export function loadDataset(repoRoot: string): Dataset {
  assertClaimRules();
  assertDefaultReplay();
  const show = showExamples();
  const ds = structuredClone(fixtureDataset) as Dataset;
  const notes: string[] = [];
  ds.results = loadResults(repoRoot, notes);
  const real = { models: false, rounds: false, replays: false, tally: false };

  if (process.env.GUARD_GYM_FORCE_FIXTURES !== "1") {
    const runsRoot = path.join(repoRoot, "runs");
    const models = loadModels(runsRoot, notes);
    const rounds = loadRounds(runsRoot, notes);
    const replays = loadReplays(runsRoot, notes);
    const tally = loadTally(runsRoot, notes);

    if (models && models !== "withheld") {
      ds.models = models.models;
      ds.example.eval = false;
      real.models = true;
      if (models.claim) ds.benchmarks.claim = models.claim;
      if (models.catch_pct != null) ds.benchmarks.catch_pct = models.catch_pct;
      if (models.cost_ratio != null) ds.benchmarks.cost_ratio = models.cost_ratio;
      if (models.point_gap != null) ds.benchmarks.point_gap = models.point_gap;
    }
    if (rounds && rounds !== "withheld") {
      ds.rounds = rounds;
      ds.example.training = false;
      real.rounds = true;
    }
    if (replays && replays !== "withheld") {
      ds.replays = replays;
      ds.example.replays = false;
      real.replays = true;
    }
    if (tally && tally !== "withheld") {
      ds.tally.items = tally;
      ds.example.tally = false;
      real.tally = true;
    }
  } else {
    notes.unshift("GUARD_GYM_FORCE_FIXTURES=1, fixtures kept");
  }

  hideSynthetic(ds, show, real);
  if (!show && ds.replays.some((replay) => replay.synthetic)) {
    throw new Error("synthetic replays leaked into a build with examples hidden");
  }
  if (!show && !real.models && ds.models.length) {
    throw new Error("synthetic benchmark scores leaked into a build with examples hidden");
  }

  const flags = Object.values(ds.example);
  const realCount = flags.filter((flag) => !flag).length;
  ds.isExample = realCount === 0;
  ds.source = realCount === 0 ? "fixtures" : realCount === flags.length ? "runs" : "mixed";
  ds.notes = notes;
  return applyDerived(ds);
}
