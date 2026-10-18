import raw from "virtual:guard-data";
import type { Dataset } from "../lib/types";

/** Must match DEV_ONLY_REPLAYS in loader/loadDataset.ts. */
const DEV_ONLY_REPLAYS = ["0142", "0207"];

/**
 * Second lock, client side: `import.meta.env.PROD` is fixed at build time, so a production bundle never
 * renders a synthetic or dev-only replay even if the build-time loader was misconfigured.
 */
export function getDataset(): Dataset {
  if (!import.meta.env.PROD) return raw;
  const replays = raw.replays.filter((replay) => !replay.synthetic && !DEV_ONLY_REPLAYS.includes(replay.id));
  return { ...raw, replays, shown: { ...raw.shown, replays: raw.shown.replays && replays.length > 0 } };
}
