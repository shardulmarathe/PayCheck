import { useInView } from "framer-motion";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { Sign, Tag } from "./Sign";
import { Bar, Row, Target, type Fx } from "./TrickScan";

/**
 * "Run a test" (Shardul 8:27): the judge picks a trick, a store skin is drawn at random, the page assembles, then two
 * lanes run on that same page: "No guard" pays and a receipt prints; "PayCheck" scans at the pay button, locks onto
 * the trick, drops the gate and stamps what it caught. Client-side only, no network calls. Labelled
 * "Illustration, recorded behavior". Prices are ILLUSTRATIVE and avoid every demo/Try-it number ($8.99/$8.69).
 * Skins reuse the six-lane replay skins (demo store skins: Desklane, Homegoods Direct, Beanbarn, Chargehub;
 * neutral: Soundnest, Voltmart). Card data is the public 4242 test card.
 */
// Only tricks r4 actually caught in the shopper runs (Researcher, 8:29). Never padded total; no subscription trap.
type TrickId = "price" | "verify" | "copycat" | "finalfee" | "plan" | "clean";
const TRICKS: { id: TrickId; button: string; label: string; why: string }[] = [
  { id: "price", button: "Price changed", label: "Price changed", why: "Checkout charges more than the product page showed." },
  { id: "verify", button: "Fake card check", label: "Fake card check", why: "A fake verification pop-up asks for your full card details and bank password again." },
  { id: "copycat", button: "Copycat pay page", label: "Copycat pay page", why: "This pay page copies the store's look but sits on a different domain." },
  { id: "finalfee", button: "Surprise final fee", label: "Surprise final fee", why: "A fee that wasn't on any earlier step appears only at the final step." },
  { id: "plan", button: "Protection plan add-on", label: "Protection plan add-on", why: "A paid protection plan was added to your order before you got to checkout." },
  { id: "clean", button: "No trick", label: "No trick found", why: "Every price matches the product page and the shipping fee was shown up front." },
];

type Skin = { cls: string; name: string; slug: string; logo?: string; mark?: "sn" | "vm"; thumb: string; product: string; price: number };
const SKINS: Skin[] = [
  { cls: "sk-dl", name: "Desklane", slug: "desklane", logo: "/skins/desklane.svg", thumb: "sk-thumb-note", product: "Dot-grid notebook, A5", price: 16 },
  { cls: "sk-hg", name: "Homegoods Direct", slug: "homegoodsdirect", logo: "/skins/homegoodsdirect.svg", thumb: "sk-thumb-kettle", product: "Enamel stovetop kettle, 2 L", price: 34 },
  { cls: "sk-bb", name: "Beanbarn", slug: "beanbarn", logo: "/skins/beanbarn.svg", thumb: "sk-thumb-bag", product: "House Medium Roast, 12 oz", price: 14 },
  { cls: "sk-ch", name: "Chargehub", slug: "chargehub", logo: "/skins/chargehub.svg", thumb: "sk-thumb-plug", product: "Wall charger, 65 W", price: 29 },
  { cls: "sk-sn", name: "soundnest", slug: "soundnest", mark: "sn", thumb: "sk-thumb-phones", product: "Studio headphones, closed-back", price: 59 },
  { cls: "sk-vm", name: "Voltmart", slug: "voltmart", mark: "vm", thumb: "sk-thumb-cable", product: "USB-C cable, 2 m", price: 24 },
];

const ADDON = 4.5;
const FEE = 5.75;
const BUMP = 3.5;
const SHIP = 4;
const usd = (n: number) => `$${n.toFixed(2)}`;
const clamp = (v: number) => Math.min(1, Math.max(0, v));
const seg = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
const easeOut = (x: number) => 1 - (1 - x) ** 3;
const back = (x: number) => (x <= 0 ? 0 : x >= 1 ? 1 : 1 + 2.8 * (x - 1) ** 3 + 1.8 * (x - 1) ** 2);

/** Timeline in ms. Build: head, product, rows, button, then the trick slotted in last and outlined. */
const T = { head: 0, item: 300, rows: 650, btn: 950, trick: 1300, outlineEnd: 2100, move: 2100, click: 3300, scan: 3300, lock: 4100, gate: 4400, stamp: 4800, end: 5600 };

const copyDomain = (skin: Skin) => `${skin.slug}-pay.test`;

function total(trick: TrickId, p: number) {
  if (trick === "plan") return p + ADDON;
  if (trick === "finalfee") return p + FEE;
  if (trick === "price") return p + BUMP;
  if (trick === "clean") return p + SHIP;
  return p;
}

/** What the unguarded run cost: one plain line for the receipt. */
function receipt(trick: TrickId, skin: Skin): { lines: [string, string][]; note: string; bad: boolean } {
  const p = skin.price;
  const tot = total(trick, p);
  switch (trick) {
    case "plan":
      return { lines: [[skin.product, usd(p)], ["Protection plan, 1 year", usd(ADDON)], ["Charged", usd(tot)]], note: `${usd(ADDON)} for a plan nobody asked for.`, bad: true };
    case "finalfee":
      return { lines: [[skin.product, usd(p)], ["Service fee", usd(FEE)], ["Charged", usd(tot)]], note: `${usd(FEE)} fee that appeared only at the last step.`, bad: true };
    case "copycat":
      return { lines: [["Paid to", copyDomain(skin)], ["Card number", "Sent"], ["Charged", usd(tot)]], note: "Paid a lookalike site, not the store.", bad: true };
    case "price":
      return { lines: [["Product page price", usd(p)], ["Charged", usd(tot)]], note: `${usd(BUMP)} more than the product page showed.`, bad: true };
    case "verify":
      return { lines: [["Card number", "Sent"], ["Expiry and CVC", "Sent"], ["Bank password", "Sent"]], note: "Full card details went to a fake verification page.", bad: true };
    default:
      return { lines: [[skin.product, usd(p)], ["Shipping", usd(SHIP)], ["Charged", usd(tot)]], note: "Matches the product page.", bad: false };
  }
}

/** The store page for a skin + trick. `t` drives the build; the trick element is wrapped in Target so the scan can lock on. */
function Store({ skin, trick, t, fx, outline }: { skin: Skin; trick: TrickId; t: number; fx: Fx; outline: boolean }) {
  const a = (at: number): CSSProperties => {
    const k = easeOut(seg(t, at, at + 320));
    return { opacity: k, transform: `translateY(${(1 - k) * 10}px)` };
  };
  const p = skin.price;
  const tot = total(trick, p);
  const domain = trick === "verify" ? `${skin.slug}-secure-verify.test` : `${skin.slug}.test/checkout`;
  const lastStep = trick === "finalfee";
  const slot = (node: ReactNode, cls: string) => (
    <div className={outline ? "rt-slot is-outlined" : "rt-slot"} style={a(T.trick)}>
      <Target fx={fx} className={cls}>
        {node}
      </Target>
    </div>
  );
  const pay = (label: string) => (
    <span className="sk-btn" data-pay style={a(T.btn)}>
      {label}
    </span>
  );
  return (
    <div className={`sk ${skin.cls} rt-sk`}>
      {trick === "copycat" ? slot(<Bar domain={`${copyDomain(skin)}/checkout`} />, "sk-urlslot") : <Bar domain={domain} />}
      <div className="sk-head" style={a(T.head)}>
        {skin.logo ? <img className="sk-logo" src={skin.logo} alt="" /> : skin.mark === "sn" ? <span className="sk-mark"><i /><i /><i /><i /></span> : <span className="sk-bolt" />}
        <span className="sk-word">{skin.name}</span>
        {lastStep ? (
          <span className="sk-step">
            Cart › Shipping › <b>Review</b>
          </span>
        ) : (
          <span className="sk-step">Checkout</span>
        )}
      </div>
      <div className="sk-body">
        <div className="sk-item" style={a(T.item)}>
          <span className={`sk-thumb ${skin.thumb}`} />
          <div>
            <p className="sk-name">{skin.product}</p>
            <p className="sk-sub">{trick === "price" ? `Product page price ${usd(p)}` : "Qty 1"}</p>
          </div>
          <b>{trick === "price" ? "" : usd(p)}</b>
        </div>
        <div className="rt-rows" style={a(T.rows)}>
          {trick !== "price" && trick !== "verify" ? <Row k="Item" v={usd(p)} /> : null}
          {trick === "finalfee" || trick === "copycat" || trick === "plan" ? <Row k="Shipping" v="Free" /> : null}
          {trick === "clean" ? <Row k="Shipping (shown on product page)" v={usd(SHIP)} /> : null}
        </div>
        {trick === "plan"
          ? slot(
              <>
                <span className="sk-check is-on">✓</span>
                <span className="sk-addon-t">
                  Protection plan, 1 year
                  <small>Added to your order</small>
                </span>
                <b>{usd(ADDON)}</b>
              </>,
              "sk-addon",
            )
          : null}
        {trick === "price" ? slot(<><span>Item price at checkout</span><b>{usd(tot)}</b></>, "sk-pricebox") : null}
        {trick === "finalfee"
          ? slot(
              <>
                <span>
                  Service fee
                  <small>Added at this step · step 3 of 3</small>
                </span>
                <b>{usd(FEE)}</b>
              </>,
              "sk-feerow",
            )
          : null}
        <div style={a(trick === "finalfee" ? T.trick : T.rows)}>
          <Row k="Total" v={usd(tot)} className="is-total" />
        </div>
        {trick === "clean" ? (
          <div className={outline ? "rt-slot is-outlined" : "rt-slot"} style={a(T.btn)}>
            <Target fx={fx} className="sk-payrow">
              {pay(`Pay ${usd(tot)}`)}
            </Target>
          </div>
        ) : trick === "verify" ? (
          <span className="sk-btn" style={a(T.btn)}>
            Pay {usd(tot)}
          </span>
        ) : (
          pay(`Pay ${usd(tot)}`)
        )}
      </div>
      {trick === "verify" ? (
        <div className={outline ? "rt-slot rt-modal-slot is-outlined" : "rt-slot rt-modal-slot"} style={a(T.trick)}>
          <Target fx={fx} className="sk-modal">
            <div className="sk-modal-h">
              <span className="sk-lock" />
              <span>Card verification required</span>
            </div>
            <p className="sk-modal-p">To protect your purchase, re-enter your full card details and your online banking password.</p>
            <label className="sk-field">
              <span>Card number</span>
              <em>4242 4242 4242 4242</em>
            </label>
            <div className="sk-fields2">
              <label className="sk-field">
                <span>Expiry</span>
                <em>12/29</em>
              </label>
              <label className="sk-field">
                <span>CVC</span>
                <em>123</em>
              </label>
            </div>
            <label className="sk-field">
              <span>Online banking password</span>
              <em>••••••••••</em>
            </label>
            <span className="sk-btn" data-pay>
              Verify and continue
            </span>
          </Target>
        </div>
      ) : null}
    </div>
  );
}

type Run = { n: number; trick: TrickId; skin: Skin };

function Lane({ run, t, guarded, payAt }: { run: Run; t: number; guarded: boolean; payAt: { x: number; y: number } | null }) {
  const info = TRICKS.find((x) => x.id === run.trick)!;
  const block = run.trick !== "clean";
  const caught = guarded && block;
  const outline = t > T.trick && t < T.outlineEnd;
  // Cursor: starts low-right, walks to the pay button.
  const walk = easeOut(seg(t, T.move, T.click - 200));
  const press = seg(t, T.click - 200, T.click) * (1 - seg(t, T.click, T.click + 160));
  const tx = payAt ? 88 + (payAt.x - 88) * walk : 88;
  const ty = payAt ? 96 + (payAt.y - 96) * walk : 96;
  // Guarded lane: scan sweeps at the pay button, locks on, the gate drops, the stamp lands.
  const scan = guarded ? easeOut(seg(t, T.scan, T.lock)) : 0;
  const snap = guarded ? back(seg(t, T.lock, T.lock + 260)) : 0;
  const x1 = caught ? easeOut(seg(t, T.lock + 200, T.lock + 380)) : 0;
  const x2 = caught ? easeOut(seg(t, T.lock + 300, T.lock + 480)) : 0;
  const gate = caught ? back(seg(t, T.gate, T.gate + 380)) : 0;
  const stamp = guarded ? seg(t, T.stamp, T.stamp + 320) : 0;
  const swing = stamp < 1 ? -18 + 14 * back(stamp) : -4;
  const fx: Fx = { block: caught, snap, x1, x2, off: (1 - snap) * 30 };
  // Unguarded (or cleared) lane pays; the receipt prints.
  const paid = !caught && t > T.click + (guarded ? 1700 : 0);
  const printAt = T.click + (guarded ? 1700 : 200);
  const print = easeOut(seg(t, printAt, printAt + 700));
  const rc = receipt(run.trick, run.skin);
  const status = guarded ? (stamp > 0 ? (caught ? "Held" : "Cleared") : t >= T.scan ? "Scanning" : t > 0 ? "Watching" : "Ready") : paid ? "Paid" : t > 0 ? "Shopping" : "Ready";
  return (
    <div className={`rt-lane ${guarded ? "is-guard" : "is-open"} ${caught ? "ts-red" : "ts-pass"}`}>
      <div className="rt-lane-h">
        <p className="rt-lane-t">{guarded ? "PayCheck" : "No guard"}</p>
        <span className={`rt-lane-s${status === "Held" ? " is-held" : ""}`}>{status}</span>
      </div>
      <div className="ts-doc rt-doc">
        <div className="ts-content">
          <Store skin={run.skin} trick={run.trick} t={t} fx={guarded ? fx : { block: false, snap: 0, x1: 0, x2: 0, off: 30 }} outline={outline} />
        </div>
        {guarded ? (
          <div className="ts-xray" style={{ clipPath: `inset(0 0 ${(100 - scan * 100).toFixed(2)}% 0)`, opacity: 1 - seg(t, T.lock + 100, T.lock + 500) }}>
            <div className="ts-content">
              <Store skin={run.skin} trick={run.trick} t={t} fx={fx} outline={false} />
            </div>
          </div>
        ) : null}
        {guarded ? <span className="ts-scan" style={{ top: `${scan * 100}%`, opacity: t > T.scan && t < T.lock ? 1 : 0 }} /> : null}
        {payAt ? (
          <span className="rt-gate" style={{ top: `${payAt.y}%`, transform: `rotate(${(1 - gate) * -80}deg)`, opacity: gate > 0 ? 1 : 0 }} aria-hidden="true">
            {Array.from({ length: 9 }, (_, i) => (
              <i key={i} />
            ))}
          </span>
        ) : null}
        <svg className="ts-cursor rt-cursor" viewBox="0 0 24 24" style={{ left: `${tx}%`, top: `${ty}%`, opacity: t > T.move && t < (caught ? T.gate + 200 : T.end) ? 1 : 0, transform: `scale(${1 - press * 0.18})` }}>
          <path d="M3 2 L20 12 L12.5 13.6 L9 21 Z" />
        </svg>
        {guarded ? (
          <span className="ts-tag-anchor rt-tag">
            <Tag
              verdict={caught ? "held" : "cleared"}
              className="ts-stamp"
              label={caught ? `✕ Caught · ${info.label}` : `✓ Allowed · ${info.label}`}
              detail={info.why}
              style={{ opacity: stamp > 0 ? Math.min(1, stamp * 3) : 0, transform: `translateY(${(1 - Math.min(1, stamp * 2)) * -14}px) rotate(${swing}deg)` }}
            />
          </span>
        ) : null}
      </div>
      <div className="rt-out">
        {paid || (!guarded && print > 0) ? (
          <p className={rc.bad ? "rt-outcome is-bad" : "rt-outcome"} style={{ opacity: print }}>
            {rc.note}
          </p>
        ) : caught && gate > 0.5 ? (
          <p className="rt-stopped">Payment stopped before any money moved.</p>
        ) : null}
      </div>
    </div>
  );
}

export function RunTest() {
  const reduced = usePrefersReducedMotion();
  const [run, setRun] = useState<Run | null>(null);
  const [t, setT] = useState(0);
  const [payAt, setPayAt] = useState<{ x: number; y: number } | null>(null);
  const raf = useRef(0);
  const lastSkin = useRef(-1);
  const measure = useRef<HTMLDivElement>(null);

  const start = useCallback(
    (trick: TrickId) => {
      cancelAnimationFrame(raf.current);
      let k = Math.floor(Math.random() * SKINS.length);
      if (k === lastSkin.current) k = (k + 1 + Math.floor(Math.random() * (SKINS.length - 1))) % SKINS.length;
      lastSkin.current = k;
      setPayAt(null);
      setRun((r) => ({ n: (r?.n ?? 0) + 1, trick, skin: SKINS[k] }));
      if (reduced) {
        setT(T.end + 2000);
        return;
      }
      const t0 = performance.now();
      setT(1);
      const tick = (now: number) => {
        const e = now - t0;
        setT(Math.max(1, e));
        if (e < T.end + 1800) raf.current = requestAnimationFrame(tick);
      };
      raf.current = requestAnimationFrame(tick);
    },
    [reduced],
  );
  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  // First run starts by itself when the section comes into view, so the lanes are never empty.
  const seen = useInView(measure, { once: true, margin: "0px 0px -30% 0px" });
  useEffect(() => {
    if (seen && !run) start("plan");
  }, [seen, run, start]);

  // Find the pay button inside the (identical) lane page, as % of the doc box, for the cursor and the gate.
  useLayoutEffect(() => {
    if (!run) return;
    const doc = measure.current?.querySelector(".rt-lane.is-open .rt-doc") as HTMLElement | null;
    const btn = doc?.querySelector("[data-pay]") as HTMLElement | null;
    if (!doc || !btn) return;
    const d = doc.getBoundingClientRect();
    const b = btn.getBoundingClientRect();
    if (!d.height) return;
    setPayAt({ x: ((b.left + b.width * 0.6 - d.left) / d.width) * 100, y: ((b.top + b.height * 0.5 - d.top) / d.height) * 100 });
  }, [run]);

  const busy = run !== null && !reduced && t < T.end;
  return (
    <div className="ts rt" ref={measure}>
      <div className="rt-top">
        <p className="rt-lede">Pick a trick. One shopper goes through without a guard, one through PayCheck.</p>
        <span className="illus-tag">Illustration</span>
      </div>
      <div className="rt-picks" role="group" aria-label="Pick a trick to test">
        {TRICKS.map((x) => (
          <button key={x.id} type="button" className={run?.trick === x.id ? "rt-pick is-on" : "rt-pick"} disabled={busy} onClick={() => start(x.id)}>
            {x.button}
          </button>
        ))}
      </div>
      {run ? (
        <div className="rt-lanes" key={run.n}>
          <Lane run={run} t={t} guarded={false} payAt={payAt} />
          <Lane run={run} t={t} guarded payAt={payAt} />
        </div>
      ) : (
        <div className="rt-lanes rt-empty" aria-hidden="true">
          <div className="rt-lane-ph">
            <p className="rt-lane-t">No guard</p>
          </div>
          <div className="rt-lane-ph">
            <p className="rt-lane-t">PayCheck</p>
          </div>
        </div>
      )}
    </div>
  );
}

/** Section 5, See it work: the one demo. */
export function SeeItWork() {
  return (
    <div className="wrap">
      <section className="section" aria-labelledby="see-title">
        <Sign n="05" id="see-title">
          See it work
        </Sign>
        <RunTest />
      </section>
    </div>
  );
}
