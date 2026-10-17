import raw from "virtual:guard-data";
import type { Dataset } from "../lib/types";

export function getDataset(): Dataset {
  return raw;
}
