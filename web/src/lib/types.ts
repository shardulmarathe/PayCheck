import type { ResultsView } from "./results";
import type { MetricId } from "./taxonomy";

export interface ModelEval {
  id: string;
  /** Long name used on latency and cost charts. */
  model: string;
  /** Short name used as a table header. */
  short: string;
  /** The fine-tuned guard. Its bar is the text color; it is never drawn as an avatar. */
  emphasis: boolean;
  pages: number;
  /** Headline catch rate, 0–100. */
  catch_rate: number;
  /** Null when this model was not scored on the full frozen set. */
  catch_rate_300: number | null;
  /** Null when this model has no 100-page slice figure. */
  catch_rate_100: number | null;
  /** Percent of clean (`none`) pages wrongly blocked. Null if unknown. */
  false_block_rate: number | null;
  /** Percent of blocks whose quoted evidence matches the labeled sentence. Null if unknown. */
  evidence_match: number | null;
  /** Null until a real eval log has a median. The UI then shows "[N] ms". */
  latency_ms_median: number | null;
  cost_per_1k_checks_usd: number;
  /** Lower end of the 95% confidence interval, catch-rate percent. Null hides the bar. */
  ci_low: number | null;
  /** Upper end of the 95% confidence interval, catch-rate percent. Null hides the bar. */
  ci_high: number | null;
  /** Catch rate 0–100 keyed by attack row id. */
  catch_rate_by_attack: Record<string, number>;
  /**
   * Optional per-attack series. When a cell is missing, the table shows an em dash
   * (latency and cost fall back to the model-level figure, because those are per check).
   */
  by_attack?: Record<string, Partial<Record<MetricId, number | null>>>;
}

export interface TrainingRound {
  /** 0 is the untuned base. */
  round: number;
  /** Catch rate on tricks like the ones in training, 0–100. */
  catch_seen: number;
  /** Catch rate on trick types held out of training, 0–100. */
  catch_heldout: number;
}

export type StepKind = "search" | "product" | "popup" | "catch" | "paid" | "click" | "other";

export interface ReplayStep {
  t_ms: number;
  id: string;
  label: string;
  /** Shown on the shared timeline. */
  tick: boolean;
  /** Red playhead dot. The label is rendered as "Caught · NN ms". */
  catch?: boolean;
  kind: StepKind;
}

export interface ReceiptLine {
  label: string;
  amount: number;
  /** Solid red fill after payment. Text switches to the page background. */
  damage?: boolean;
  muted?: boolean;
}

export interface Verdict {
  action: "allow" | "block";
  /** Null in fixtures. A real replay log fills this; the UI never invents one. */
  latency_ms: number | null;
  category: "upsell" | "scam" | string;
  trick: string;
  evidence: string;
  steer: string;
  expected_total: number;
  /** Catch-moment label, e.g. "BLOCKED · UPSELL, SNEAKED INTO BASKET". */
  readout: string;
}

export interface CartScene {
  kind: "cart";
  search_url: string;
  search_query: string;
  product_url: string;
  cart_url: string;
  /** Address drawn on the kiosk screen. Falls back to cart_url when omitted. */
  checkout_url?: string;
  product_mark: string;
  product_title: string;
  product_price: string;
  qty_label: string;
  cart_label: string;
  cart_total: string;
  cart_note: string;
  popup_title: string;
  popup_body: string;
  popup_fine_print: string;
  popup_primary: string;
  popup_dismiss: string;
}

export interface ScamScene {
  kind: "scam";
  product_url_prefix: string;
  product_url_flag: string;
  product_url_suffix: string;
  verify_url_prefix: string;
  verify_url_flag: string;
  verify_url_suffix: string;
  brand: string;
  product_name: string;
  product_price: string;
  headline: string;
  body: string;
  fields: string[];
  submit?: string;
  order_label: string;
  order_item: string;
  order_price: string;
  flagged_prefix: string;
  /** Characters shown before the letter flip. */
  flagged_from?: string;
  flagged_mark: string;
  flagged_suffix: string;
  flagged_real: string;
  trick_body: string;
}

export interface LaneCopy {
  kicker: string;
  story_label: string;
  story_body: string;
  story_title: string;
  lines: ReceiptLine[];
  paid_label: string;
  paid: number;
  paid_note: string;
  outcome: "lost" | "ok";
}

interface ReplayBase {
  id: string;
  title: string;
  budget: number;
  kicker: string;
  meta_right: string;
  shopper: string;
  duration_ms: number;
  steps: ReplayStep[];
  verdict: Verdict;
  timeline_caption: string;
  /** True on fixtures and on any runs file that is not a real recording. */
  synthetic: boolean;
  /** Dollars paid above the expected total. Matches shopper `overcharge_usd` / `dollars_lost`. */
  overcharge_usd: number;
  /** True when card or bank details were submitted on a phishing page. */
  exposed: boolean;
  /** Unwanted subscription, including shopper `final_cart.subscription`. */
  subscription: boolean;
  /**
   * Monthly price when the trap names one. `shopper/schema/replay.json` has no
   * monthly field, so this stays null unless the showcase replay supplies it.
   */
  subscription_monthly_usd: number | null;
}

export interface UpsellReplay extends ReplayBase {
  scene: "upsell";
  scene_view: CartScene;
  without: LaneCopy;
  with: LaneCopy;
}

export interface ScamReplay extends ReplayBase {
  scene: "scam";
  scene_view: ScamScene;
  columns: {
    flagged_label: string;
    trick_label: string;
    steer_label: string;
  };
}

export type Replay = UpsellReplay | ScamReplay;

export interface TallyItem {
  id: string;
  label: string;
  with_guard: number;
  without_guard: number;
  format: "count" | "dollars";
  note: string;
  /** "loss" marks the unguarded "from" figure in red, with the words still carrying the meaning. */
  from_tone: "loss" | "muted";
}

export interface CitationFigure {
  label: string;
  value: string;
  tone: "text" | "muted" | "loss";
}

export interface CitationBlock {
  id: string;
  kicker: string;
  figures?: CitationFigure[];
  stat?: { value: string; tone: "loss" | "text" };
  body: string;
  source: string;
}

export interface ProcessStep {
  n: string;
  title: string;
  body: string;
  meta: string;
}

export interface FutureItem {
  n: string;
  title: string;
  body: string;
  status: string;
}

export interface ExampleFlags {
  /** True when that block is still fixture data. Labels render only while `shown` is also true. */
  eval: boolean;
  training: boolean;
  replays: boolean;
  tally: boolean;
}

/** Headline from `runs/r{N}/summary.json` → `test.heldout_template`. Rates are percents. Null hides that slot. */
export interface HeadlineRates {
  /** True once a summary file for some round parsed. Fixture catch rates do not fill these slots. */
  from_summary: boolean;
  round: number | null;
  catch_rate: number | null;
  false_block_rate: number | null;
}

/** One train or dev page from `runs/r{N}/replay.jsonl`. Test pages are not in this file. */
export interface RoundReplayLine {
  round: number;
  page_id: string;
  store: string;
  page_kind: string;
  trick: string;
  split: "train" | "dev";
  label: string;
  verdict: string;
  correct: boolean;
  fed_back: boolean;
  source: "fresh" | "from_miss";
}

export interface RoundReplay {
  round: number;
  /** False when this round only had a replay log. */
  has_summary: boolean;
  catch_rate: number | null;
  false_block_rate: number | null;
  lines: RoundReplayLine[];
}

export interface BrowserUseRun {
  id: string;
  errand_id: string;
  mode: "unguarded" | "guarded";
  scripted: boolean;
  /** "Scripted", or the real provenance fields joined as stored. */
  provenance: string;
  attack_type: string;
  overcharge_usd: number;
  /** Public URL under `/recordings/`, or null when no MP4 is on disk. */
  video: string | null;
}

export interface BrowserUseResults {
  /** Percents. Null hides that side. */
  paid_for_trick: { unguarded: number | null; guarded: number | null };
  /** Percent of clean guarded runs where the guard blocked. Null hides the slot. */
  false_block_rate: number | null;
  /** Dollars. Null hides that side. */
  overpaid: { unguarded: number | null; guarded: number | null };
  runs: BrowserUseRun[];
}

export interface VisaStage {
  key: "agent_request" | "store_signature" | "guard" | "decision";
  label: string;
  text: string;
}

export interface VisaTrace {
  id: string;
  stages: VisaStage[];
}

export interface ShownSections {
  /** False hides the Benchmarks page and its nav link. */
  benchmarks: boolean;
  /** False hides the recorded replays. The landing is then the tagline and the kiosk. */
  replays: boolean;
  /** False hides the training-round statistic. The design-process page stays. */
  training: boolean;
  /** False drops tally numbers. The tally strip is not drawn. */
  tally: boolean;
}

export interface Dataset {
  /**
   * True only when every numeric section is still the fixture.
   * Per-section flags live on `example` and drive the "example data" labels.
   */
  isExample: boolean;
  source: "fixtures" | "runs" | "mixed";
  example: ExampleFlags;
  /** What production (or dev) is allowed to render. Synthetic sections are omitted when examples are off. */
  shown: ShownSections;
  notes: string[];
  hero: {
    eyebrow: string;
    guard_label: string;
    guard: string;
    checks_label: string;
    checks: string;
    median_label: string;
    median_catch_ms: number | null;
  };
  replays: Replay[];
  tally: { kicker: string; items: TallyItem[] };
  citations: { kicker: string; title: string; blocks: CitationBlock[] };
  benchmarks: {
    kicker: string;
    title_lines: string[];
    body: string;
    test_pages: number;
    roster: { label: string; title: string; detail: string }[];
    training_title: string;
    seen_legend: string;
    heldout_legend: string;
    latency_title: string;
    latency_note: string;
    cost_kicker: string;
    cost_headline: string;
    /**
     * "beats" only when the JSON says so. Anything else, including a missing
     * field, renders the "within" headline.
     */
    claim: "within" | "beats";
    /** Guard catch rate for the headline. Null renders the literal [X]. */
    catch_pct: number | null;
    /** Claude cost divided by the guard cost. Null renders the literal [N]. */
    cost_ratio: number | null;
    /**
     * Guard catch rate minus Claude's, in points. Positive means the guard is
     * ahead. Null renders [N] in the headline and [+N] on the gap line.
     */
    point_gap: number | null;
    /** True while [N] and [X] are still literal placeholders. */
    cost_placeholder: boolean;
    cost_note: string;
    cost_annotation: string;
    cost_axis: string;
    hollow_caption: string;
    attack_kicker: string;
    attack_title: string;
    attack_caption: string;
    summary_kicker: string;
    summary_title: string;
    summary_note: string;
  };
  rounds: TrainingRound[];
  models: ModelEval[];
  /**
   * Slice claims. Empty slices and a null cost ratio mean production has no
   * publishable results (the checked-in file is synthetic).
   */
  results: ResultsView;
  /** Held-out template rates from the latest `runs/r{N}/summary.json`. */
  headline: HeadlineRates;
  /** One entry per round that had a summary or a replay log. */
  round_replay: RoundReplay[];
  browser_use: BrowserUseResults;
  visa: VisaTrace[];
  process: {
    kicker: string;
    title_lines: string[];
    body: string;
    sources_label: string;
    sources: { title: string; detail: string }[];
    feeds_label: string;
    nodes: { n: string; title: string; detail: string; place: "left" | "right" | "bottom" }[];
    /**
     * Round index printed in the ring. Null stays the `r[n]` placeholder.
     * Training-round files do not fill this.
     */
    round_n: number | null;
    /**
     * New-layout test score, the headline number. Null stays `[X]%`.
     * Never copy a training-round catch rate into this field.
     */
    new_layout_pct: number | null;
    caught_caption: string;
    steps_kicker: string;
    steps: ProcessStep[];
    plug_kicker: string;
    plug_title_lines: string[];
    plug_body: string;
    request_label: string;
    request_code: string;
    response_label: string;
    endpoint_note: string;
  };
  future: {
    kicker: string;
    title_lines: string[];
    body: string;
    items: FutureItem[];
  };
  footer_note: string;
}
