import fs from "node:fs";
import path from "node:path";
import type { BrowserUseResults, BrowserUseRun, HeadlineRates, RoundReplay, RoundReplayLine, VisaScene, VisaTrace } from "../src/lib/types";

const REPLAY_KEYS = [
  "round",
  "page_id",
  "store",
  "page_kind",
  "trick",
  "split",
  "label",
  "verdict",
  "correct",
  "fed_back",
  "source",
] as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

/**
 * Train summaries store rates as fractions in [0, 1]. A value above 1 is already a percent.
 * Null and anything outside 0–100 stays null so the slot can hide.
 */
export function percentFromRate(value: unknown): number | null {
  const n = num(value);
  if (n == null || n < 0) return null;
  const percent = n <= 1 ? n * 100 : n;
  if (percent > 100) return null;
  return Math.round(percent * 100) / 100;
}

function scorePair(raw: unknown): { catch_rate: number | null; false_block_rate: number | null } {
  if (!isRecord(raw)) return { catch_rate: null, false_block_rate: null };
  return {
    catch_rate: percentFromRate(raw.catch_rate),
    false_block_rate: percentFromRate(raw.false_block_rate),
  };
}

export function parseReplayLine(raw: unknown): RoundReplayLine | undefined {
  if (!isRecord(raw)) return undefined;
  const round = num(raw.round);
  const pageId = str(raw.page_id);
  if (round == null || !Number.isInteger(round) || !pageId) return undefined;
  if (raw.split !== "train" && raw.split !== "dev") return undefined;
  if (raw.source !== "fresh" && raw.source !== "from_miss") return undefined;
  if (typeof raw.correct !== "boolean" || typeof raw.fed_back !== "boolean") return undefined;
  for (const key of REPLAY_KEYS) {
    if (!(key in raw)) return undefined;
  }
  return {
    round,
    page_id: pageId,
    store: typeof raw.store === "string" ? raw.store : "",
    page_kind: typeof raw.page_kind === "string" ? raw.page_kind : "",
    trick: typeof raw.trick === "string" ? raw.trick : "",
    split: raw.split,
    label: typeof raw.label === "string" ? raw.label : "",
    verdict: typeof raw.verdict === "string" ? raw.verdict : "",
    correct: raw.correct,
    fed_back: raw.fed_back,
    source: raw.source,
  };
}

export function readReplayLines(file: string): RoundReplayLine[] {
  if (!fs.existsSync(file)) return [];
  const lines: RoundReplayLine[] = [];
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    try {
      const parsed = parseReplayLine(JSON.parse(trimmed) as unknown);
      if (parsed) lines.push(parsed);
    } catch {
      /* A bad line is skipped. The rest of the round still plays. */
    }
  }
  return lines;
}

export function readSummaryFile(file: string): { round: number; catch_rate: number | null; false_block_rate: number | null } | undefined {
  if (!fs.existsSync(file)) return undefined;
  try {
    const raw = JSON.parse(fs.readFileSync(file, "utf8")) as unknown;
    if (!isRecord(raw) || !Number.isInteger(num(raw.round))) return undefined;
    const heldout = isRecord(raw.test) ? raw.test.heldout_template : undefined;
    const scores = scorePair(heldout);
    return { round: num(raw.round) as number, ...scores };
  } catch {
    return undefined;
  }
}

function roundDirs(root: string): string[] {
  if (!fs.existsSync(root)) return [];
  return fs
    .readdirSync(root)
    .filter((name) => /^r\d+$/.test(name))
    .map((name) => path.join(root, name));
}

export function loadRoundReplays(roots: string[]): RoundReplay[] {
  const byRound = new Map<number, RoundReplay>();
  for (const root of roots) {
    for (const dir of roundDirs(root)) {
      const summary = readSummaryFile(path.join(dir, "summary.json"));
      const lines = readReplayLines(path.join(dir, "replay.jsonl"));
      const fromName = Number(/^r(\d+)$/.exec(path.basename(dir))?.[1]);
      const round = summary?.round ?? (lines[0]?.round != null ? lines[0].round : Number.isInteger(fromName) ? fromName : undefined);
      if (round == null || (!summary && lines.length === 0)) continue;
      byRound.set(round, {
        round,
        has_summary: !!summary,
        catch_rate: summary?.catch_rate ?? null,
        false_block_rate: summary?.false_block_rate ?? null,
        lines: lines.some((line) => line.round === round) ? lines.filter((line) => line.round === round) : lines,
      });
    }
  }
  return [...byRound.values()].sort((a, b) => a.round - b.round);
}

export function headlineFromRounds(rounds: RoundReplay[]): HeadlineRates {
  const latest = [...rounds].reverse().find((round) => round.has_summary);
  if (!latest) return { from_summary: false, round: null, catch_rate: null, false_block_rate: null };
  return {
    from_summary: true,
    round: latest.round,
    catch_rate: latest.catch_rate,
    false_block_rate: latest.false_block_rate,
  };
}

function provenanceOf(raw: Record<string, unknown>): { scripted: boolean; label: string } | undefined {
  if (raw.provenance === "scripted") return { scripted: true, label: "Scripted" };
  if (!isRecord(raw.provenance) || raw.provenance.kind !== "real") return undefined;
  const model = str(raw.provenance.model);
  const timestamp = str(raw.provenance.timestamp);
  const version = str(raw.provenance.browser_use_version);
  if (!model || !timestamp || !version) return undefined;
  return { scripted: false, label: `${model} · ${timestamp} · ${version}` };
}

function paidForTrick(raw: Record<string, unknown>): boolean {
  const scams = Array.isArray(raw.scams_fallen_for) ? raw.scams_fallen_for.length : 0;
  const lost = num(raw.dollars_lost) ?? num(raw.overcharge_usd) ?? 0;
  return raw.outcome === "fell" || lost > 0 || scams > 0 || raw.unwanted_subscription === true;
}

function facedTrick(raw: Record<string, unknown>): boolean {
  const attack = str(raw.attack_type);
  return !!attack && attack !== "none";
}

function cleanRun(raw: Record<string, unknown>): boolean {
  const attack = raw.attack_type;
  return attack == null || attack === "" || attack === "none";
}

function guardBlocked(raw: Record<string, unknown>): boolean {
  if (!Array.isArray(raw.steps)) return false;
  return raw.steps.some((step) => isRecord(step) && step.blocked === true);
}

function recordingUrl(raw: Record<string, unknown>, recordingsDir: string): string | null {
  const names: string[] = [];
  if (typeof raw.video === "string" && raw.video.toLowerCase().endsWith(".mp4")) names.push(path.basename(raw.video));
  const errand = str(raw.errand_id);
  const mode = raw.mode === "unguarded" || raw.mode === "guarded" ? raw.mode : undefined;
  if (errand && mode) names.push(`${errand}_${mode}.mp4`);
  const runId = str(raw.run_id);
  if (runId) names.push(`${runId}.mp4`);
  for (const name of names) {
    if (fs.existsSync(path.join(recordingsDir, name))) return `/recordings/${name}`;
  }
  return null;
}

interface ShopperFile {
  file: string;
  mtime: number;
  raw: Record<string, unknown>;
}

function collectShopper(roots: string[]): ShopperFile[] {
  const found: ShopperFile[] = [];
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "shots") continue;
        walk(full);
        continue;
      }
      if (!entry.name.endsWith(".json") || entry.name === "tally.json" || entry.name === "ledger.json") continue;
      try {
        const raw = JSON.parse(fs.readFileSync(full, "utf8")) as unknown;
        if (!isRecord(raw)) continue;
        if (raw.mode !== "unguarded" && raw.mode !== "guarded") continue;
        if (!provenanceOf(raw) || num(raw.overcharge_usd) == null) continue;
        found.push({ file: full, mtime: fs.statSync(full).mtimeMs, raw });
      } catch {
        /* skip */
      }
    }
  };
  for (const root of roots) walk(root);
  return found;
}

export function loadBrowserUse(roots: string[], recordingsDir: string, showExamples: boolean): BrowserUseResults {
  const empty: BrowserUseResults = {
    paid_for_trick: { unguarded: null, guarded: null },
    false_block_rate: null,
    overpaid: { unguarded: null, guarded: null },
    runs: [],
  };
  const ranked = collectShopper(roots).sort((a, b) => b.mtime - a.mtime);
  const seen = new Set<string>();
  const runs: BrowserUseRun[] = [];
  const kept: Record<string, unknown>[] = [];
  for (const item of ranked) {
    const provenance = provenanceOf(item.raw);
    if (!provenance) continue;
    if (!showExamples && (provenance.scripted || item.raw.synthetic === true)) continue;
    const runId = str(item.raw.run_id) ?? path.basename(item.file);
    const mode = item.raw.mode as "unguarded" | "guarded";
    const key = `${runId}:${mode}:${str(item.raw.errand_id) ?? ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    kept.push(item.raw);
    runs.push({
      id: `${str(item.raw.errand_id) ?? runId}-${mode}`,
      errand_id: str(item.raw.errand_id) ?? runId,
      mode,
      scripted: provenance.scripted,
      provenance: provenance.label,
      attack_type: typeof item.raw.attack_type === "string" ? item.raw.attack_type : "",
      overcharge_usd: num(item.raw.overcharge_usd) ?? 0,
      video: recordingUrl(item.raw, recordingsDir),
    });
  }
  if (!runs.length) return empty;

  const rate = (mode: "unguarded" | "guarded", pick: (raw: Record<string, unknown>) => boolean, base: (raw: Record<string, unknown>) => boolean) => {
    const rows = kept.filter((raw) => raw.mode === mode && base(raw));
    if (!rows.length) return null;
    return percentFromRate(rows.filter(pick).length / rows.length);
  };

  const overpaid = (mode: "unguarded" | "guarded") => {
    const rows = kept.filter((raw) => raw.mode === mode);
    if (!rows.length) return null;
    const total = rows.reduce((sum, raw) => sum + (num(raw.overcharge_usd) ?? 0), 0);
    return Math.round(total * 100) / 100;
  };

  const cleanGuarded = kept.filter((raw) => raw.mode === "guarded" && cleanRun(raw));
  return {
    paid_for_trick: {
      unguarded: rate("unguarded", paidForTrick, facedTrick),
      guarded: rate("guarded", paidForTrick, facedTrick),
    },
    false_block_rate: cleanGuarded.length ? percentFromRate(cleanGuarded.filter(guardBlocked).length / cleanGuarded.length) : null,
    overpaid: { unguarded: overpaid("unguarded"), guarded: overpaid("guarded") },
    runs,
  };
}

/** The approved heading. The trace file's own title is never printed in its place. */
export const VISA_HEADING = "Signed agent check (our implementation of Visa's Trusted Agent Protocol)";

/** Fixed demo lookup (visa-run/visa/video.py TRICK_LABELS, from demo/shell-spec.md). */
const TRICK_LABELS: Record<string, string> = {
  preselected_addon: "Pre-ticked add-on",
  hidden_fees: "Hidden fee",
  price_change: "Price changed",
  fake_card_verification: "Fake card check",
  subscription_trap: "Subscription trap",
  none: "No trick found",
};

/** Scene order on screen: browse → clean → disclosed fee → raised → tampered → unsigned. */
const SCENE_ORDER: RegExp[] = [/^agent shops|browse/i, /^clean/i, /disclosed fee/i, /raised/i, /tamper/i, /unsigned/i];

function sceneRank(title: string): number {
  const rank = SCENE_ORDER.findIndex((pattern) => pattern.test(title));
  return rank === -1 ? SCENE_ORDER.length : rank;
}

/**
 * Raw request material never reaches the page: anything that looks like a URL, host:port, header,
 * key id, nonce, tag, signature value or timing is dropped, even when it sits in a whitelisted field.
 */
const RAW_REQUEST = [
  /:\/\//,
  /\blocalhost\b|\b\d{1,3}(\.\d{1,3}){3}\b/i,
  /:\d{2,5}\b/,
  /\b(key_?id|keyid|nonce|tag|created|expires|alg)\s*[=:]/i,
  /\bsig\d*\s*=|signature-input\s*:|signature\s*:/i,
  /\b[A-Za-z0-9+/_-]{32,}={0,2}/,
  /\b\d+(\.\d+)?\s*ms\b/i,
  /^\s*(GET|POST|PUT|PATCH|DELETE)\s+\//,
  /(^|\s)\/[a-z0-9_-]+(\?|\/)/i,
];

export function safeText(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const text = value.trim();
  if (!text || text.length > 240) return null;
  return RAW_REQUEST.some((pattern) => pattern.test(text)) ? null : text;
}

function trickLabel(value: unknown): string | null {
  const text = safeText(value);
  if (!text) return null;
  return TRICK_LABELS[text] ?? text;
}

function parseScene(raw: unknown): VisaScene | undefined {
  if (!isRecord(raw)) return undefined;
  const title = safeText(raw.title);
  if (!title) return undefined;
  const sig = isRecord(raw.signature) ? raw.signature : {};
  const status = num(raw.store_status);
  const accepted = sig.accepted === true;
  let guard: VisaScene["guard"] = null;
  if (accepted && isRecord(raw.guard) && (raw.guard.verdict === "allow" || raw.guard.verdict === "block")) {
    guard = { verdict: raw.guard.verdict, trick: trickLabel(raw.guard.trick), evidence: safeText(raw.guard.evidence) };
  }
  return {
    title,
    check: { accepted, status: status != null && Number.isInteger(status) ? status : null, reason: safeText(sig.reason) },
    guard,
    paid: raw.paid === true,
  };
}

/**
 * Reads a sanitized trace (runs/visa/trace-trimmed.json shape). Only whitelisted keys are read;
 * every other key in the file is ignored, so raw request fields can't render even if present.
 */
export function parseVisa(raw: unknown, id: string): VisaTrace | undefined {
  if (!isRecord(raw) || !Array.isArray(raw.scenes)) return undefined;
  const scenes = raw.scenes
    .map(parseScene)
    .filter((scene): scene is VisaScene => !!scene)
    .map((scene, index) => ({ scene, index }))
    .sort((a, b) => sceneRank(a.scene.title) - sceneRank(b.scene.title) || a.index - b.index)
    .map(({ scene }) => scene);
  if (!scenes.length) return undefined;
  const guard = safeText(raw.guard) ?? "r4 (8-bit copy)";
  const gate = safeText(raw.gate_format) ?? "fixed gate";
  const payment = safeText(raw.payment) ?? "mock";
  return { id, heading: VISA_HEADING, footer: `guard: ${guard}, ${gate} · ${payment} payment`, scenes };
}

function collectJson(roots: string[]): string[] {
  const files: string[] = [];
  const walk = (dir: string) => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.name.endsWith(".json") && entry.name !== "index.json") files.push(full);
    }
  };
  for (const root of roots) walk(root);
  return files.sort();
}

export function loadVisa(roots: string[], showExamples: boolean): VisaTrace[] {
  const traces: VisaTrace[] = [];
  for (const file of collectJson(roots)) {
    try {
      const raw = JSON.parse(fs.readFileSync(file, "utf8")) as unknown;
      if (isRecord(raw) && raw.synthetic === true && !showExamples) continue;
      const id = isRecord(raw) && str(raw.id) ? (str(raw.id) as string) : path.basename(file, ".json");
      const trace = parseVisa(raw, id);
      if (trace) traces.push(trace);
    } catch {
      /* skip */
    }
  }
  return traces;
}
