import path from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vite";
import { loadDataset } from "./loader/loadDataset";
import { PRODUCT_NAME, TAGLINE } from "./src/lib/product";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

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
      console.log(`[guard-data] source=${data.source} isExample=${data.isExample}${note}`);
      return `export default ${JSON.stringify(data)};`;
    },
  };
}

function htmlConstants(): Plugin {
  return {
    name: "html-constants",
    transformIndexHtml(html) {
      return html.replaceAll("__PRODUCT_NAME__", PRODUCT_NAME).replaceAll("__TAGLINE__", TAGLINE);
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
