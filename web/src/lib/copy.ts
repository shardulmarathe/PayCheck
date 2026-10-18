
/**
 * Hero result. All r4 live AI-shopper runs.
 * Never call it "test set" or "test". No honest-checkout figure.
 */
export const HERO_RESULT = {
  // Source: r4 live AI-shopper runs.
  line: "Without a guard, AI shoppers fell for the trick 133 of 238 times. With PayCheck, 18 of 234.",
  scope: "All r4 live AI-shopper runs (Browser Use agents on our practice stores).",
  bars: [
    { label: "Without a guard", n: 133, of: 238, tone: "loss" },
    { label: "With PayCheck", n: 18, of: 234, tone: "guard" },
  ],
};

export type HeroClip = { webm: string; mp4: string; poster: string; caption: string };
export const HERO_CLIP_FAKECARD: HeroClip = {
  webm: "/recordings/hero-loop-fakecard-clean.webm",
  mp4: "/recordings/hero-loop-fakecard-clean.mp4",
  poster: "/recordings/hero-loop-fakecard-clean.png",
  caption:
    "Replay: a fake card check on the attacker's page. Without a guard, the shopper entered card details. PayCheck blocked it and said why, so it stopped before the card details were sent.",
};
export const HERO_CLIP: HeroClip = HERO_CLIP_FAKECARD;
export const SPEED_CHECKS = 257;
export const TRY_IT_URL: string | null = null;

export const DEMO_PAGES: { title: string; verdict: "BLOCK" | "PASS" }[] = [
  { title: "Protection plan add-on", verdict: "BLOCK" },
  { title: "Surprise final fee", verdict: "BLOCK" },
  { title: "Price raised at checkout", verdict: "BLOCK" },
  { title: "Fake card check", verdict: "BLOCK" },
  { title: "Honest optional add-on", verdict: "PASS" },
  { title: "Honest shipping fee", verdict: "PASS" },
  { title: "Honest price drop", verdict: "PASS" },
  { title: "Subscription switched on", verdict: "BLOCK" },
];

/**
 * Training loop (high level): one cycle, a pass counter 1..6, one caption. No per-round numbers.
 * Six rounds; r4 shipped. The attacker is a seeded template generator, not an LLM.
 */
export const LOOP = {
  kicker: "Processing line · How PayCheck was built",
  passes: 6,
  shipped: 4,
  caption: "We went around the loop 6 times and shipped round 4.",
  intake: [
    { k: "IN", title: "Practice stores", body: "Generated stores, each hiding one trick next to an honest twin. Trick text from the ec-darkpattern dataset, built on Mathur et al., \"Dark Patterns at Scale\" (Princeton, 2019)." },
    { k: "LOCK", title: "Test pages locked away", body: "300 checkout pages, half with a hidden trick, half honest, split off before training." },
  ],
  // Wording and order around the cycle. Never "LLM". No per-round numbers.
  stations: [
    { k: "01", viz: "attack", short: "Attack", title: "Attacker agent", body: "Generates trick pages." },
    { k: "02", viz: "shop", short: "Shop", title: "Browser Use agent", body: "AI shoppers run errands on our practice stores, with and without PayCheck." },
    { k: "03", viz: "score", short: "Score", title: "Evaluator", body: "Scores what the guard got right and wrong." },
    { k: "04", viz: "train", short: "Train", title: "Training (on Veri)", body: "Qwen3-4B, a small open model, trained on veri.studio. Mistakes go into the next round." },
  ],
  // Output: same trick names as Run a test.
  catches: {
    k: "OUT",
    title: "What it catches",
    items: ["Price changed", "Fake card check", "Copycat pay page", "Surprise final fee", "Protection plan add-on"],
  },
};

/**
 * Evidence: shopping agents already fail. Sources: The Washington Post, SusBench (63–87%), WebDecept (75–100%).
 * No other numbers.
 */
/**
 * Big-picture row and incidents row.
 * Each item follows its "Do not say" note. Left out on purpose: Adobe 693.4%, Visa 4,700%.
 */
export type BigStat =
  | { kind: "count"; prefix: string; to: number; suffix: string; tag: string | null; label: string; source: string; href: string }
  | { kind: "quote"; quote: string; label: string; source: string; href: string };
export const EVIDENCE = {
  kicker: "The problem",
  bigStats: [
    {
      // FORECAST; "up to", "could", US retail, 2030. Never "today", never "agents will spend".
      kind: "count",
      prefix: "$",
      to: 1,
      suffix: "T",
      tag: "Forecast",
      label: "By 2030, AI agents could orchestrate up to $1 trillion of US retail sales.",
      source: "McKinsey & Company, Oct 17, 2025",
      href: "https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-agentic-commerce-opportunity-how-ai-agents-are-ushering-in-a-new-era-for-consumers-and-merchants",
    },
    {
      // Verbatim. "possible", subscription services only; never "checkouts" or "illegal".
      kind: "count",
      prefix: "",
      to: 76,
      suffix: "%",
      tag: null,
      label: "Regulators checked 642 subscription sites and apps. Nearly 76% used at least one possible dark pattern.",
      source: "FTC with ICPEN and GPEN, Jul 10, 2024",
      href: "https://www.ftc.gov/news-events/news/press-releases/2024/07/ftc-icpen-gpen-announce-results-review-use-dark-patterns-affecting-subscription-services-privacy",
    },
    {
      // Quote verbatim. No claim that Atlas lost anyone's money.
      kind: "quote",
      quote: "Prompt injection, much like scams and social engineering on the web, is unlikely to ever be fully \u201csolved\u201d.",
      label: "OpenAI, on attacks hidden in web pages against its own browser agent.",
      source: "OpenAI, Dec 22, 2025",
      href: "https://openai.com/index/hardening-atlas-against-prompt-injection/",
    },
  ] as BigStat[],
  studiesTitle: "What the studies found",
  title: "Shopping agents already fall for checkout tricks.",
  cards: [
    {
      n: "01",
      head: "Left a paid add-on ticked",
      stat: "63–87%",
      statK: "of the time",
      body: "On real shopping sites seeded with a pre-checked paid add-on, Browser Use agents left it selected 63–87% of the time.",
      why: "Pre-checked add-ons are one of the trick types PayCheck was trained to flag.",
      source: "SusBench, IUI 2026",
      href: "https://doi.org/10.1145/3742413.3789111",
    },
    {
      n: "02",
      head: "Paid a padded total",
      stat: "75–100%",
      statK: "of the time",
      body: "In a test store where the checkout total was quietly raised above the item prices, five shopping agents still checked out 75–100% of the time, even when told to stop if the total looked wrong.",
      why: "A warning in the agent's instructions isn't enough on its own. That's why PayCheck is a separate check on the page, not another line in the prompt.",
      source: "WebDecept, ACL 2026",
      href: "https://aclanthology.org/2026.acl-long.1009/",
    },
  ],
};

export const SITE = {
  /** Caption follows the active clip (HERO_CLIP.caption). */
  heroClipCaption: HERO_CLIP.caption,
  howTitle: "One check before your agent pays.",
  howSteps: [
    { n: "01", title: "The agent reaches checkout", body: "Before it pays, it sends the page to PayCheck." },
    { n: "02", title: "PayCheck reads the page", body: "A small open model checks the page for a hidden trick. How it was trained is under How we trained it." },
    { n: "03", title: "Pass, or block and say why", body: "On a block, the agent is told the trick and doesn't pay." },
  ],
  accuracyKicker: "Results",
  accuracyTitle: "Matches Claude Haiku 5.5 on overall accuracy.",
  accuracyCalibration: "With a threshold calibrated on our attacker dev set.",
  /** F1 at the calibrated threshold. */
  accuracyF1: { paycheck: "0.78", haiku: "0.77" },
  accuracyF1Label: "Overall accuracy (F1)",
  accuracyTrainedWin: "Level with Claude Haiku 5.5, or slightly ahead, on the attack types it was trained on",
  accuracyTrainedDelta: "+0.07 F1",
  /** Full-load cost: PayCheck $0.1282 vs Claude Haiku 5.5 $0.2248 per 1,000 checks.
   *  Never put a speed figure in the same sentence: the 0.7 s figure is normal load; at full load a typical check took 2.9 s. */
  accuracyCostKicker: "Cost",
  accuracyCostDelta: "$0 vs $0.22",
  accuracyCostUnit: "per 1,000 checks, on your Mac or phone vs Claude Haiku 5.5",
  accuracyCostWin: "Cheaper than Claude Haiku 5.5",
  // Source detail kept here only: best case, at full load, one busy T4 server (7,882 checks/hour).
  accuracyCostNote: "",
  accuracyCostAria:
    "Cheaper than Claude Haiku 5.5: $0 per 1,000 checks on your own Mac or phone, vs $0.22 for Claude Haiku 5.5.",
  heroTrickLine: "The trick: a fake verification page asks for your full card details and online banking password.",
  heroOutcomeUnguarded: "Handed over card details",
  heroOutcomeGuarded: "Blocked before paying",
  heroOutcomeGuardedReason: "Fake card check",
  heroSteps: ["Checkout", "Card check", "Result"],
  heroVerdict: "Better than Claude Haiku 5.5 for checkout safety.",
  heroReasons: [
    "0 vs 16 honest checkouts blocked (of 150)",
    "Level with it, or slightly ahead, on the attack types it was trained on",
    "Matches it on overall accuracy (0.78 vs 0.77)",
    "0.7s vs 1.5s on a typical check",
    "Cheaper per check",
  ],
  heroVerdictLink: "See the results",
  accuracyLead:
    "PayCheck never blocked an honest page on our 300-page benchmark (0 of 150; Claude Haiku 5.5: 11%).",
  accuracyTest: "The test: 300 checkout pages, half with a hidden trick, half honest.",
  accuracyOrigin:
    "How the pages were made: generated stores whose trick text comes from the ec-darkpattern dataset, built on Mathur et al., \"Dark Patterns at Scale\" (Princeton, 2019). Test pages were split off before training.",
  accuracyFootnote: "Each model was graded once. Claude Haiku 5.5 ran with a higher token limit.",
  fullResultsLink: "Full benchmark results",
  speedTitle: "How fast",
  speedLine: "PayCheck answered in 0.7 seconds on a typical check, vs 1.5 seconds for Claude Haiku 5.5. Its slowest 5% of checks took 2.1 seconds, vs 3.1 for Claude Haiku 5.5.",
  speedStats: [
    { who: "PayCheck", ours: true, typical: 0.7, slowest: 2.1 },
    { who: "Claude Haiku 5.5", ours: false, typical: 1.5, slowest: 3.1 },
  ],
  speedUnit: "seconds",
  speedTypicalLabel: "on a typical check",
  speedSlowestLabel: "slowest 5% of checks",
  speedNote: `PayCheck: time on our guard server only (one T4 GPU, ${SPEED_CHECKS} checks during live shopper runs). Claude Haiku 5.5: full API round trip from our computer, including network (300 benchmark pages). Not measured the same way.`,
  tryTitle: "See it decide.",
  tryKicker: "Try it",
  tryBody: "Eight pages from our practice store, protected by PayCheck. Five hide a trick; three are honest.",
  tryButton: "Open the hands-on demo",
  tryNote: "Designed demo pages, not a benchmark. Same verdict on every page in each of 3 runs.",
  visaKicker: "Trust & payments",
  tracksTitle: "Tracks we're entering",
  tracks: ["Model Learning (main track)", "Visa", "veri.studio", "Browser Use"],
  builtTitle: "Built with",
  builtWith: ["Browser Use", "Visa's Trusted Agent Protocol (our implementation)", "Modal", "veri.studio", "Qwen3-4B"],
  futureKicker: "What's next",
  futureTitle: "What PayCheck learns next.",
  futureTitles: ["Learns from its own misses", "Reads the whole checkout", "Built into agent frameworks"],
  futureItems: [
    "An attacker that writes new trick pages from the guard's misses, so each round trains on the tricks it got wrong.",
    "Multi-page context so padded totals and folded-in fees become catchable.",
    "A default pre-payment hook inside agent frameworks, paired with signed agent identity.",
  ],
  futureDevice: {
    title: "Runs on your own device",
    body: "Run on your own device, PayCheck would be faster, cheaper and more secure than a cloud AI check. The checkout page and card details never leave your machine, there's no API bill per check, and no network round trip to wait on. For financial services, that means banks and card networks can screen agent payments without sending customer data to an outside AI company, which keeps sensitive data in-house, simplifies privacy and compliance reviews, and keeps costs flat as checks grow into the millions.",
  },
};
