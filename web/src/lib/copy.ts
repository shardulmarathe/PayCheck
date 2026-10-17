/**
 * Claim lines a real eval can replace. The Benchmarks headline and the
 * landing comparison caption live here, not in the fixtures.
 */
export const COPY = {
  benchmarksHeadline: ["Near-frontier catch rate,", "at a fraction of the cost."] as const,
  comparisonCaption(budgetLabel: string, addonPrice: string, example: boolean): string {
    const line = `Same errand, same ${budgetLabel} budget. The only difference is the ${addonPrice} add-on the guard caught.`;
    return example ? `${line} Example data.` : line;
  },
};
