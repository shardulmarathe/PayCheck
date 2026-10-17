/** Trick ids shared with runs/ JSON. Popup add-on and pre-checked extra are both preselected_addon variants. */
export const TRICK_IDS = [
  "hidden_fees",
  "preselected_addon",
  "price_change",
  "subscription_trap",
  "copycat_domain",
  "fake_card_verification",
  "listing_injection",
  "none",
] as const;

export type TrickId = (typeof TRICK_IDS)[number];

export const TRAINED_ON = [
  "hidden_fees",
  "preselected_addon",
  "price_change",
  "subscription_trap",
  "fake_card_verification",
] as const;

export const HELD_OUT = ["copycat_domain", "listing_injection"] as const;

export type AttackFamily = "upsell" | "scam";

export interface AttackRow {
  id: string;
  trick: TrickId;
  label: string;
  family: AttackFamily;
  heldOut: boolean;
}

export const ATTACK_ROWS: AttackRow[] = [
  { id: "popup_add_on", trick: "preselected_addon", label: "Popup add-on", family: "upsell", heldOut: false },
  { id: "prechecked_extra", trick: "preselected_addon", label: "Pre-checked extra", family: "upsell", heldOut: false },
  { id: "subscription_trap", trick: "subscription_trap", label: "Subscription trap", family: "upsell", heldOut: false },
  { id: "hidden_fees", trick: "hidden_fees", label: "Hidden fee", family: "upsell", heldOut: false },
  { id: "price_change", trick: "price_change", label: "Price change at checkout", family: "upsell", heldOut: false },
  { id: "copycat_domain", trick: "copycat_domain", label: "Copycat domain", family: "scam", heldOut: true },
  { id: "fake_card_verification", trick: "fake_card_verification", label: "Fake verify-card page", family: "scam", heldOut: false },
  { id: "listing_injection", trick: "listing_injection", label: "Listing prompt injection", family: "scam", heldOut: true },
];

export const METRICS = [
  { id: "catch_rate", label: "Catch rate" },
  { id: "false_block_rate", label: "False blocks" },
  { id: "evidence_match", label: "Evidence match" },
  { id: "latency_ms", label: "Latency" },
  { id: "cost_per_1k_checks_usd", label: "Cost per 1k" },
] as const;

export type MetricId = (typeof METRICS)[number]["id"];
