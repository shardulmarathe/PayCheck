export interface TryPage {
  id: string;
  title: string;
  expected: "BLOCK" | "PASS";
  url: string;
  domain: string;
  kind: string;
  store: string;
  heading: string | null;
  listed: string | null;
  was: string | null;
  items: { label: string; amount: string }[];
  checks: { label: string; amount: string | null; checked: boolean }[];
  notes: { text: string; where: "before" | "after" }[];
  total: string | null;
  button: string | null;
  response: { verdict: string; trick: string; evidence: string; instruction: string };
  runs: string[];
  src: { guard_text_md5: string; fallback_md5: string };
  verify?: { badge: string; heading: string; body: string; fields: string[] };
}
