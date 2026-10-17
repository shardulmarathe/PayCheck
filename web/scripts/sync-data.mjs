import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repo = process.env.GUARD_GYM_ROOT
  ? path.resolve(process.env.GUARD_GYM_ROOT)
  : path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const examples = process.argv.includes("--examples");
const runsRoot = path.join(repo, "runs");
const dataRoot = path.join(repo, "web", "public", "data");
const recordingsRoot = path.join(repo, "web", "public", "recordings");

function resetDir(dir) {
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });
}

function copyFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return undefined;
  }
}

function scriptedOrSynthetic(raw) {
  if (!raw || typeof raw !== "object") return false;
  if (raw.synthetic === true) return true;
  if (raw.provenance === "scripted") return true;
  return false;
}

function walk(dir, visit) {
  if (!fs.existsSync(dir)) return;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, visit);
    else visit(full, entry.name);
  }
}

resetDir(path.join(dataRoot, "rounds"));
resetDir(path.join(dataRoot, "browser-use"));
resetDir(path.join(dataRoot, "visa"));
resetDir(recordingsRoot);

const manifest = { rounds: [], browser_use: [], visa: [], recordings: [] };

if (fs.existsSync(runsRoot)) {
  for (const name of fs.readdirSync(runsRoot).filter((entry) => /^r\d+$/.test(entry)).sort()) {
    let wrote = false;
    for (const file of ["summary.json", "replay.jsonl"]) {
      const src = path.join(runsRoot, name, file);
      if (!fs.existsSync(src)) continue;
      copyFile(src, path.join(dataRoot, "rounds", name, file));
      wrote = true;
    }
    if (wrote) manifest.rounds.push(name);
  }
}

const copiedVideos = new Set();
function copyRecording(src) {
  if (!src || !fs.existsSync(src) || !src.toLowerCase().endsWith(".mp4")) return;
  const base = path.basename(src);
  if (copiedVideos.has(base)) return;
  copyFile(src, path.join(recordingsRoot, base));
  copiedVideos.add(base);
  manifest.recordings.push(base);
}

function copyShopper(file) {
  const raw = readJson(file);
  if (!raw || (raw.mode !== "unguarded" && raw.mode !== "guarded")) return;
  if (!examples && scriptedOrSynthetic(raw)) return;
  const destName = path.basename(file);
  copyFile(file, path.join(dataRoot, "browser-use", destName));
  manifest.browser_use.push(destName);
  if (typeof raw.video === "string") {
    const beside = path.resolve(path.dirname(file), raw.video);
    copyRecording(beside);
    copyRecording(path.join(runsRoot, raw.video));
  }
  const errand = typeof raw.errand_id === "string" ? raw.errand_id : "";
  if (errand) copyRecording(path.join(path.dirname(file), `${errand}_${raw.mode}.mp4`));
}

walk(path.join(runsRoot, "shopper"), (file, name) => {
  if (name.endsWith(".json") && name !== "tally.json" && name !== "ledger.json") copyShopper(file);
});

walk(path.join(runsRoot, "visa"), (file, name) => {
  if (!name.endsWith(".json")) return;
  const raw = readJson(file);
  if (!examples && raw && raw.synthetic === true) return;
  const destName = path.basename(file);
  copyFile(file, path.join(dataRoot, "visa", destName));
  manifest.visa.push(destName);
});

walk(path.join(runsRoot, "recordings"), (file, name) => {
  if (name.toLowerCase().endsWith(".mp4")) copyRecording(file);
});

fs.writeFileSync(path.join(dataRoot, "index.json"), `${JSON.stringify(manifest, null, 2)}\n`);
fs.writeFileSync(path.join(dataRoot, ".gitkeep"), "");
fs.writeFileSync(path.join(recordingsRoot, ".gitkeep"), "");
console.log(`synced ${manifest.rounds.length} rounds, ${manifest.browser_use.length} browser-use runs, ${manifest.visa.length} visa traces, ${manifest.recordings.length} recordings`);
