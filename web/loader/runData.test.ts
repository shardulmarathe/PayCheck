import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { headlineFromRounds, loadBrowserUse, loadRoundReplays, loadVisa, percentFromRate } from "./runData";

const line = {
  round: 1,
  page_id: "p-a11ce003",
  store: "Northmart",
  page_kind: "cart",
  trick: "preselected_addon",
  split: "dev",
  label: "block",
  verdict: "pass",
  correct: false,
  fed_back: true,
  source: "fresh",
};

test("fractions become percents and null stays hidden", () => {
  assert.equal(percentFromRate(0.87), 87);
  assert.equal(percentFromRate(1), 100);
  assert.equal(percentFromRate(0), 0);
  assert.equal(percentFromRate(91), 91);
  assert.equal(percentFromRate(null), null);
  assert.equal(percentFromRate(undefined), null);
});

test("summary headline is heldout_template and a missing rate stays null", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "rounds-"));
  fs.mkdirSync(path.join(root, "r1"));
  fs.writeFileSync(
    path.join(root, "r1", "summary.json"),
    JSON.stringify({
      round: 1,
      winner_trial: null,
      new_pages: 1,
      seeded_from_misses: 0,
      train: { catch_rate: 1, false_block_rate: 0, f1: 1, n: 1 },
      dev: { catch_rate: 0, false_block_rate: 0, f1: 0, n: 1 },
      test: {
        in_dist: { catch_rate: 1, false_block_rate: 0, f1: 1, n: 2 },
        heldout_template: { catch_rate: 0.5, false_block_rate: null, f1: 0, n: 2 },
        heldout_attack: { catch_rate: 0, false_block_rate: null, f1: 0, n: 2 },
      },
      in_dist_vs_heldout_template_gap: 1,
    }),
  );
  fs.writeFileSync(path.join(root, "r1", "replay.jsonl"), `${JSON.stringify(line)}\n`);
  fs.mkdirSync(path.join(root, "r2"));
  fs.writeFileSync(path.join(root, "r2", "replay.jsonl"), `${JSON.stringify({ ...line, round: 2 })}\n`);
  const rounds = loadRoundReplays([root]);
  const headline = headlineFromRounds(rounds);
  assert.equal(headline.from_summary, true);
  assert.equal(headline.round, 1);
  assert.equal(headline.catch_rate, 50);
  assert.equal(headline.false_block_rate, null);
  assert.equal(rounds[0]?.lines[0]?.fed_back, true);
  assert.equal(rounds[1]?.has_summary, false);
});

test("browser use aggregates rates and drops scripted runs when examples are off", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "shopper-"));
  const recordings = fs.mkdtempSync(path.join(os.tmpdir(), "recordings-"));
  const write = (name: string, raw: unknown) => fs.writeFileSync(path.join(root, name), JSON.stringify(raw));
  const base = {
    schema_version: "1",
    errand_id: "hero-batteries",
    run_id: "run-1",
    attack_type: "preselected_addon",
    outcome: "fell",
    overcharge_usd: 9.99,
    dollars_lost: 9.99,
    scams_fallen_for: ["addon"],
    unwanted_subscription: false,
    steps: [],
    video: null,
  };
  write("unguarded.json", { ...base, mode: "unguarded", synthetic: false, provenance: { kind: "real", model: "haiku", timestamp: "2026-10-17T00:00:00Z", browser_use_version: "0.5.0" } });
  write("guarded.json", {
    ...base,
    mode: "guarded",
    outcome: "protected",
    overcharge_usd: 0,
    dollars_lost: 0,
    scams_fallen_for: [],
    synthetic: false,
    provenance: { kind: "real", model: "haiku", timestamp: "2026-10-17T00:00:00Z", browser_use_version: "0.5.0" },
  });
  write("clean.json", {
    ...base,
    errand_id: "clean-soap",
    run_id: "run-2",
    mode: "guarded",
    attack_type: "none",
    outcome: "clean",
    overcharge_usd: 0,
    dollars_lost: 0,
    scams_fallen_for: [],
    steps: [{ blocked: true }],
    synthetic: false,
    provenance: { kind: "real", model: "haiku", timestamp: "2026-10-17T00:00:00Z", browser_use_version: "0.5.0" },
  });
  write("scripted.json", { ...base, run_id: "scripted", mode: "unguarded", synthetic: true, provenance: "scripted", overcharge_usd: 50 });
  fs.writeFileSync(path.join(recordings, "hero-batteries_unguarded.mp4"), "");
  const hidden = loadBrowserUse([root], recordings, false);
  assert.equal(hidden.runs.some((run) => run.scripted), false);
  assert.equal(hidden.paid_for_trick.unguarded, 100);
  assert.equal(hidden.paid_for_trick.guarded, 0);
  assert.equal(hidden.false_block_rate, 100);
  assert.equal(hidden.overpaid.unguarded, 9.99);
  assert.equal(hidden.overpaid.guarded, 0);
  assert.equal(hidden.runs.find((run) => run.mode === "unguarded")?.video, "/recordings/hero-batteries_unguarded.mp4");
  assert.equal(hidden.runs.find((run) => run.mode === "unguarded")?.provenance, "haiku · 2026-10-17T00:00:00Z · 0.5.0");
  const shown = loadBrowserUse([root], recordings, true);
  assert.equal(shown.runs.some((run) => run.provenance === "Scripted"), true);
});

test("visa trace keeps the four stages and hides a missing one", () => {
  const traces = [
    {
      synthetic: false,
      id: "checkout-1",
      signed_agent_request: { nonce: "abc" },
      store_signature_check: { ok: true },
      guard_check: { verdict: "block" },
      decision: "block",
    },
  ];
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "visa-"));
  fs.writeFileSync(path.join(root, "trace.json"), JSON.stringify(traces[0]));
  fs.writeFileSync(path.join(root, "partial.json"), JSON.stringify({ signed_agent_request: { nonce: "x" }, decision: "pay" }));
  fs.writeFileSync(path.join(root, "example.json"), JSON.stringify({ synthetic: true, decision: "block" }));
  const hidden = loadVisa([root], false);
  const full = hidden.find((trace) => trace.id === "checkout-1");
  const partial = hidden.find((trace) => trace.id === "partial");
  assert.equal(hidden.length, 2);
  assert.deepEqual(full?.stages.map((stage) => stage.label), [
    "Signed agent request",
    "Store signature check",
    "Guard check",
    "Block",
  ]);
  assert.deepEqual(partial?.stages.map((stage) => stage.label), ["Signed agent request", "Pay"]);
  assert.equal(hidden.some((trace) => trace.id === "example"), false);
});
