import { PRODUCT_NAME } from "./product";

/**
 * Claim lines a real eval can replace. The Sonnet sentence is built in
 * `results.ts` from slice claims, not from a hardcoded cost ratio.
 */
export const COPY = {
  catchLine(catchPct: string): string {
    return `Catches ${catchPct}% of checkout tricks.`;
  },
  falseBlockLine(falseBlockPct: string): string {
    return `False-blocks ${falseBlockPct}% of clean pages.`;
  },
  useCase(addonPrice: string): string {
    return `You ask your AI agent to buy batteries. The checkout slips in a ${addonPrice} add-on. ${PRODUCT_NAME} stops it before your agent pays.`;
  },
  comparisonCaption(budgetLabel: string, addonPrice: string, example: boolean): string {
    const line = `Same errand, same ${budgetLabel} budget. The only difference is the ${addonPrice} add-on the guard caught.`;
    return example ? `${line} Example data.` : line;
  },
};
