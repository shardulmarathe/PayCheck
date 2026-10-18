/**
 * "Real incidents" row in The problem section. Verified wording from the parent (8:32), word for word; quotes unchanged.
 * Swap wording here only. Source URLs as given, no utm params.
 * Three cards only (Shardul 8:33), equal size, Operator first. Never "the AI bought the wrong item".
 */
export type Incident = {
  name: string;
  date: string;
  /** Small tag shown when the agent isn't a shopping agent. */
  tag?: string;
  body: string;
  /** Extra approved line kept word for word (card 1: Shardul requires the "likely because" line). */
  detail?: string;
  quote: string;
  speaker?: string;
  /** Source line as shown, and the links behind it. */
  sourceLine: string;
  links: { label: string; href: string }[];
  /** Headline money figure; the card with one renders as the big card. */
  figure?: string;
  /** Round 18 chip text (Shardul 9:06): a few words after "name · date". */
  chip?: string;
};

export const INCIDENTS_TITLE = "Real incidents";

export const INCIDENTS: Incident[] = [
  {
    name: "OpenAI Operator",
    chip: "bought eggs unprompted, $31.43",
    date: "Feb 2025",
    body: "Asked only to find cheap eggs, OpenAI's Operator bought them unprompted for $31.43, and the price it reported wasn't the price it paid, likely because the checkout page hid the fees.",
    quote: "I never asked Operator to actually buy the eggs.",
    sourceLine: "The Washington Post, Feb 7, 2025",
    links: [{ label: "The Washington Post", href: "https://www.washingtonpost.com/technology/2025/02/07/openai-operator-ai-agent-chatgpt/" }],
  },
  {
    name: "Amazon Buy for Me",
    chip: "wrong items",
    date: "Jan 2026",
    body: "Amazon's experimental Buy for Me AI copied a small shop's listings without asking and bought on shoppers' behalf. The listings didn't always match the real product, so holiday buyers got the wrong items.",
    quote: "People ordering these Christmas gifts and holiday gifts were getting the wrong items and demanding refunds",
    speaker: "Sarah Burzio, owner, Hitchcock Paper Co.",
    sourceLine: "Bloomberg via Tech Xplore, Jan 2026",
    links: [{ label: "Bloomberg", href: "https://techxplore.com/news/2026-01-amazon-ai-tool-blindsides-merchants.html" }],
  },
  {
    name: "Instinct",
    chip: "20 lb of wings",
    date: "Oct 2026",
    body: "Asked to order chicken wings and drumsticks with no amount given, the Instinct AI agent delivered 20 pounds of wings.",
    quote: "We were shamelessly eating chicken wings for about five or six days straight for every meal",
    speaker: "Austin Welch, Instinct user",
    sourceLine: "Business Insider, Oct 10, 2026",
    links: [{ label: "Business Insider", href: "https://www.businessinsider.com/ai-agents-instinct-muse-redefine-personal-shopping-online-2026-10" }],
  },
];

/**
 * "Security research" row (Shardul 8:45): Guardio + Microsoft. Each card tagged with what it is.
 * Guardio copy word for word from /workspace/final/aux/citations/BIG-PROBLEM.md 0.1 (lines 11-18); never say it
 * happened every time or to a real user. Microsoft copy word for word from 0.3 (lines 29-36); never "all AI agents".
 */
export const SIMULATIONS_TITLE = "Security research";

export const SIMULATIONS: Incident[] = [
  {
    name: "Guardio Labs",
    chip: "paid a fake Walmart (researcher test)",
    date: "Aug 2025",
    tag: "Researcher test store, not a real victim",
    figure: "1 prompt",
    body: "Security researchers told an AI browser \u201cBuy me an Apple Watch.\u201d It paid a fake Walmart store with the saved card.",
    quote: "It found the Apple Watch, added it to the cart, and, without asking for confirmation, autofilled our saved address and credit card details from the browser's auto-fill database. Seconds later, the \"purchase\" was complete.",
    sourceLine: "Guardio Labs, \u201cScamlexity\u201d, Aug 20, 2025",
    links: [{ label: "Guardio Labs, \u201cScamlexity\u201d, Aug 20, 2025", href: "https://guard.io/labs/scamlexity-we-put-agentic-ai-browsers-to-the-test-they-clicked-they-paid-they-failed" }],
  },
  {
    name: "Microsoft Magentic Marketplace",
    chip: "every payment redirected (simulation)",
    date: "Nov 2025",
    tag: "Simulation, no real money",
    figure: "Every payment redirected",
    body: "In Microsoft's simulated marketplace, a fake seller's prompt injection redirected every payment from three AI shopper models, including a 4B model.",
    quote: "GPT-4o, GPTOSS-20b and Qwen3-4b were very vulnerable to prompt injection: all payments were redirected to the manipulative agent under these conditions.",
    sourceLine: "Microsoft Research blog, Nov 5, 2025",
    links: [{ label: "Microsoft Research blog", href: "https://www.microsoft.com/en-us/research/blog/magentic-marketplace-an-open-source-simulation-environment-for-studying-agentic-markets/" }],
  },
];
