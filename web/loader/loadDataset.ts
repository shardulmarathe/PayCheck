import fs from "node:fs";
import path from "node:path";
import { formatLatency, trimNum } from "../src/lib/format";
import type {
  Dataset,
  ModelEval,
  Replay,
  TallyItem,
  TrainingRound,
  Verdict,
} from "../src/lib/types";
import { fixtureDataset } from "./fixtures";

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
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
    catch_rate_by_attack: numMap(raw.catch_rate_by_attack) ?? {},
    by_attack: byAttack,
  };
}

function loadModels(runsRoot: string, notes: string[]): ModelEval[] | undefined {
  const evalDir = path.join(runsRoot, "eval");
  const leaderboard = readJson(path.join(evalDir, "leaderboard.json"), notes);
  const rawModels: unknown[] = [];
  if (isRecord(leaderboard) && Array.isArray(leaderboard.models)) {
    rawModels.push(...leaderboard.models);
  } else if (Array.isArray(leaderboard)) {
    rawModels.push(...leaderboard);
  }
  if (rawModels.length === 0) {
    for (const file of listJson(evalDir)) {
      if (path.basename(file) === "leaderboard.json") continue;
      const parsed = readJson(file, notes);
      if (isRecord(parsed) && Array.isArray(parsed.models)) rawModels.push(...parsed.models);
      else if (parsed) rawModels.push(parsed);
    }
  }
  if (rawModels.length === 0) return undefined;
  const models = rawModels
    .map((raw, index) => normalizeModel(raw, notes, `eval model ${index}`))
    .filter((model): model is ModelEval => !!model);
  return models.length ? models : undefined;
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

function loadRounds(runsRoot: string, notes: string[]): TrainingRound[] | undefined {
  const fromFiles: TrainingRound[] = [];
  for (const file of listJson(path.join(runsRoot, "training"))) {
    const parsed = readJson(file, notes);
    const items = Array.isArray(parsed) ? parsed : [parsed];
    fromFiles.push(...takeRounds(items, notes, path.basename(file)));
  }
  if (fromFiles.length) {
    fromFiles.sort((a, b) => a.round - b.round);
    return fromFiles;
  }

  const fromEval: TrainingRound[] = [];
  for (const file of listJson(path.join(runsRoot, "eval"))) {
    const parsed = readJson(file, notes);
    if (!isRecord(parsed) || !Array.isArray(parsed.rounds)) continue;
    fromEval.push(...takeRounds(parsed.rounds, notes, path.basename(file)));
  }
  if (!fromEval.length) return undefined;
  fromEval.sort((a, b) => a.round - b.round);
  return fromEval;
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

function isReplay(value: unknown): value is Replay {
  if (!isRecord(value) || !str(value.id) || !str(value.title) || !Array.isArray(value.steps)) return false;
  if (!isVerdict(value.verdict) || num(value.duration_ms) == null || num(value.budget) == null) return false;
  if (!isRecord(value.scene_view) || (value.scene_view.kind !== "cart" && value.scene_view.kind !== "scam")) {
    return false;
  }
  if (value.scene === "upsell") return isRecord(value.without) && isRecord(value.with);
  if (value.scene === "scam") return isRecord(value.columns);
  return false;
}

function loadReplays(runsRoot: string, notes: string[]): Replay[] | undefined {
  const dir = path.join(runsRoot, "replays");
  const replays: Replay[] = [];
  for (const file of listJson(dir)) {
    const parsed = readJson(file, notes);
    const items = Array.isArray(parsed) ? parsed : [parsed];
    for (const item of items) {
      if (isReplay(item)) replays.push(item);
      else if (item) notes.push(`${path.basename(file)} is not a replay`);
    }
  }
  return replays.length ? replays : undefined;
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

function loadTally(runsRoot: string, notes: string[]): TallyItem[] | undefined {
  const parsed = readJson(path.join(runsRoot, "tally.json"), notes);
  const items = isRecord(parsed) && Array.isArray(parsed.items) ? parsed.items : Array.isArray(parsed) ? parsed : [];
  if (!items.length) return undefined;
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

  const gemini = ds.models.find((model) => model.id === "gemini" || /gemini/i.test(model.model));
  if (!ds.example.eval && guard && gemini && guard.cost_per_1k_checks_usd > 0) {
    const pts = Math.abs(gemini.catch_rate - guard.catch_rate);
    const ahead = guard.catch_rate > gemini.catch_rate;
    const ratio = gemini.cost_per_1k_checks_usd / guard.cost_per_1k_checks_usd;
    ds.benchmarks.cost_annotation = `1/${trimNum(ratio)} the cost · ${trimNum(pts)} pts ${ahead ? "ahead" : "behind"}`;
    ds.benchmarks.cost_placeholder = false;
  }
  return ds;
}

/** Build-time dataset. Real runs/ JSON replaces a section; everything else stays on fixtures. */
export function loadDataset(repoRoot: string): Dataset {
  const ds = structuredClone(fixtureDataset) as Dataset;
  const notes: string[] = [];
  if (process.env.GUARD_GYM_FORCE_FIXTURES === "1") {
    ds.notes = ["GUARD_GYM_FORCE_FIXTURES=1, fixtures kept"];
    return applyDerived(ds);
  }

  const runsRoot = path.join(repoRoot, "runs");
  const models = loadModels(runsRoot, notes);
  const rounds = loadRounds(runsRoot, notes);
  const replays = loadReplays(runsRoot, notes);
  const tally = loadTally(runsRoot, notes);

  if (models) {
    ds.models = models;
    ds.example.eval = false;
  }
  if (rounds) {
    ds.rounds = rounds;
    ds.example.training = false;
  }
  if (replays) {
    ds.replays = replays;
    ds.example.replays = false;
  }
  if (tally) {
    ds.tally.items = tally;
    ds.example.tally = false;
  }

  const flags = Object.values(ds.example);
  const real = flags.filter((flag) => !flag).length;
  ds.isExample = real === 0;
  ds.source = real === 0 ? "fixtures" : real === flags.length ? "runs" : "mixed";
  ds.notes = notes;
  return applyDerived(ds);
}
