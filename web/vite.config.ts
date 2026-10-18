import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vite";
import { loadDataset } from "./loader/loadDataset";
import { DESCRIPTOR, PRODUCT_NAME, SITE_TITLE, TAGLINE } from "./src/lib/product";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const SITE_MODELS: Record<string, string> = {
  guard: "PayCheck",
  "claude-haiku": "Claude Haiku 5.5",
  "qwen-base": "Qwen3-4B before training",
};

function siteBundle(data: ReturnType<typeof loadDataset>) {
  return {
    isExample: data.isExample,
    source: data.source,
    example: data.example,
    shown: { ...data.shown, replays: false, training: false, tally: false },
    replays: [],
    models: data.models
      .filter((model) => model.id in SITE_MODELS)
      // Compliance: the unseen-trick-type slice score is never shipped or shown. Only the approved
      // public line may speak to unseen tricks, so `display.unseen` is dropped from the bundle here.
      .map((model) => ({ id: model.id, model: SITE_MODELS[model.id], short: SITE_MODELS[model.id], display: model.display ? { f1: model.display.f1, catch: model.display.catch, false_blocks: model.display.false_blocks } : undefined })),
    visa: data.visa.map((trace) => ({ ...trace, footer: "PayCheck guard, 8-bit copy · mock payments" })),
    // The site's What's next reads lib/copy.ts; the pack's future items are not rendered and one carries a
    // generalization claim, so none of them ship.
    future: { ...data.future, items: [] },
    footer_note: data.footer_note,
  };
}

function guardDataPlugin(): Plugin {
  const virtual = "virtual:guard-data";
  const resolved = `\0${virtual}`;
  return {
    name: "guard-data",
    resolveId(id) {
      if (id === virtual) return resolved;
      return null;
    },
    load(id) {
      if (id !== resolved) return null;
      const data = loadDataset(repoRoot);
      const note = data.notes.length ? ` notes=${data.notes.join(" | ")}` : "";
      console.log(`[guard-data] source=${data.source} isExample=${data.isExample} shown=${JSON.stringify(data.shown)}${note}`);
      return `export default ${JSON.stringify(process.env.NODE_ENV === "production" ? siteBundle(data) : data)};`;
    },
  };
}

function htmlConstants(): Plugin {
  return {
    name: "html-constants",
    transformIndexHtml(html) {
      return html
        .replaceAll("__SITE_TITLE__", SITE_TITLE)
        .replaceAll("__PRODUCT_NAME__", PRODUCT_NAME)
        .replaceAll("__DESCRIPTOR__", DESCRIPTOR)
        .replaceAll("__TAGLINE__", TAGLINE);
    },
  };
}

const port = Number(process.env.PORT) || 5173;

export default defineConfig({
  plugins: [react(), guardDataPlugin(), htmlConstants()],
  resolve: {
    alias: [{ find: /^three$/, replacement: path.resolve(path.dirname(fileURLToPath(import.meta.url)), "vendor/three-lite.js") }],
  },
  server: { host: "0.0.0.0", port },
  preview: { host: "0.0.0.0", port },
});
