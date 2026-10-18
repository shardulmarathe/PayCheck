import type { MotionValue } from "framer-motion";
import { useDriver } from "./motion/Pin";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import type { ReactNode } from "react";
import { Tag } from "./Sign";

/**
 * Every trick type on the site, caught in turn on a checkout page, then one honest page allowed (no repeats).
 * Each lane is a DIFFERENT store with its own skin (demo store skins where they exist: Desklane, Homegoods Direct,
 * Beanbarn, Chargehub; Soundnest and Voltmart are neutral skins),
 * and each shows the actual trick on the page. The scan bracket lands on the offending element; the tag says what it found.
 * Prices are ILLUSTRATIVE (Illustration tag) and deliberately match no demo clip or Try-it number. Card data is the public
 * 4242 test card, not real. Decorative (aria-hidden).
 */
type SceneId = "addon" | "fee" | "price" | "verify" | "sub" | "clean";
interface ScanScene {
  id: SceneId;
  store: string;
  domain: string;
  verdict: "block" | "pass";
  label: string;
  /** One plain sentence naming what the scan found. */
  why: string;
}

const SCENES: ScanScene[] = [
  { id: "addon", store: "Desklane", domain: "desklane.test/checkout", verdict: "block", label: "Pre-ticked add-on", why: "A paid protection plan was ticked for you before you got to checkout." },
  { id: "fee", store: "Homegoods Direct", domain: "homegoodsdirect.test/checkout", verdict: "block", label: "Hidden fee", why: "A service fee that was never listed shows up only in the final total." },
  { id: "price", store: "Beanbarn", domain: "beanbarn.test/checkout", verdict: "block", label: "Price changed", why: "Checkout charges more than the product page showed." },
  { id: "verify", store: "Chargehub Secure Verify", domain: "chargehub-secure-verify.test", verdict: "block", label: "Fake card check", why: "A fake verification pop-up asks for your full card details and bank password again." },
  { id: "sub", store: "Soundnest", domain: "soundnest.test/checkout", verdict: "block", label: "Subscription trap", why: "Small print turns this one-time purchase into a monthly charge." },
  { id: "clean", store: "Voltmart", domain: "voltmart.test/checkout", verdict: "pass", label: "No trick found", why: "Every price matches the product page and the shipping fee was shown up front." },
];

const clamp = (v: number) => Math.min(1, Math.max(0, v));
const seg = (t: number, a: number, b: number) => clamp((t - a) / (b - a));
const easeOut = (x: number) => 1 - (1 - x) ** 3;
const back = (x: number) => {
  const c1 = 1.8;
  const c3 = c1 + 1;
  return x <= 0 ? 0 : x >= 1 ? 1 : 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2;
};

export type Fx = { block: boolean; snap: number; x1: number; x2: number; off: number };

/** The offending element: stays in store colour above the x-ray, gets the scan bracket and (on a block) the X. */
export function Target({ fx, children, className = "" }: { fx: Fx; children: ReactNode; className?: string }) {
  return (
    <div className={`ts-target ${className}`}>
      {children}
      <span className="ts-brk" style={{ opacity: fx.snap > 0 ? 1 : 0 }}>
        {[0, 1, 2, 3].map((i) => (
          <i key={i} style={{ translate: `${(i % 2 ? 1 : -1) * fx.off}px ${(i < 2 ? -1 : 1) * fx.off}px` }} />
        ))}
      </span>
      {fx.block ? (
        <svg className="ts-x">
          <line x1="3%" y1="8%" x2="97%" y2="92%" pathLength="1" style={{ strokeDashoffset: 1 - fx.x1 }} />
          <line x1="97%" y1="8%" x2="3%" y2="92%" pathLength="1" style={{ strokeDashoffset: 1 - fx.x2 }} />
        </svg>
      ) : null}
    </div>
  );
}

export function Bar({ domain }: { domain: string }) {
  return (
    <div className="sk-bar">
      <i />
      <i />
      <i />
      <span>{domain}</span>
    </div>
  );
}

export function Row({ k, v, className }: { k: ReactNode; v: ReactNode; className?: string }) {
  return (
    <div className={className ? `sk-row ${className}` : "sk-row"}>
      <span>{k}</span>
      <b>{v}</b>
    </div>
  );
}

function Content({ scene, fx }: { scene: ScanScene; fx: Fx }) {
  switch (scene.id) {
    case "addon":
      return (
        <div className="sk sk-dl">
          <Bar domain={scene.domain} />
          <div className="sk-head">
            <img className="sk-logo" src="/skins/desklane.svg" alt="" />
            <span className="sk-word">Desklane</span>
            <span className="sk-step">Cart › <b>Checkout</b> › Done</span>
          </div>
          <div className="sk-body sk-split">
            <div className="sk-item">
              <span className="sk-thumb sk-thumb-note" />
              <div>
                <p className="sk-name">Dot-grid notebook, A5</p>
                <p className="sk-sub">Qty 1 · Navy cloth</p>
              </div>
              <b>$16.00</b>
            </div>
            <div className="sk-sum">
              <p className="sk-sum-h">Order summary</p>
              <Row k="Notebook" v="$16.00" />
              <Target fx={fx} className="sk-addon">
                <span className="sk-check is-on">✓</span>
                <span className="sk-addon-t">
                  Desk Protection Plan, 1 year
                  <small>Added to your order</small>
                </span>
                <b>$4.50</b>
              </Target>
              <Row k="Total" v="$20.50" className="is-total" />
              <span className="sk-btn">Place order</span>
            </div>
          </div>
        </div>
      );
    case "fee":
      return (
        <div className="sk sk-hg">
          <Bar domain={scene.domain} />
          <div className="sk-head">
            <img className="sk-logo" src="/skins/homegoodsdirect.svg" alt="" />
            <span className="sk-word">Homegoods Direct</span>
            <span className="sk-step">Secure checkout</span>
          </div>
          <div className="sk-body">
            <p className="sk-h">Review your order</p>
            <div className="sk-item">
              <span className="sk-thumb sk-thumb-kettle" />
              <div>
                <p className="sk-name">Enamel stovetop kettle, 2 L</p>
                <p className="sk-sub">Listed at $34.00</p>
              </div>
              <b>$34.00</b>
            </div>
            <Row k="Shipping" v="Free" />
            <Row k="Subtotal" v="$34.00" />
            <Target fx={fx} className="sk-totalrow">
              <span>
                Total
                <small>incl. service &amp; handling $5.75</small>
              </span>
              <b>$39.75</b>
            </Target>
            <span className="sk-btn">Pay now</span>
          </div>
        </div>
      );
    case "price":
      return (
        <div className="sk sk-bb">
          <Bar domain={scene.domain} />
          <div className="sk-announce">Fresh roasted every Tuesday</div>
          <div className="sk-head">
            <img className="sk-logo" src="/skins/beanbarn.svg" alt="" />
            <span className="sk-word">Beanbarn</span>
          </div>
          <div className="sk-body sk-compare">
            <div className="sk-was">
              <p className="sk-mini">On the product page</p>
              <span className="sk-thumb sk-thumb-bag" />
              <p className="sk-name">House Medium Roast, 12 oz</p>
              <p className="sk-price">$14.00</p>
            </div>
            <span className="sk-arrow">→</span>
            <div className="sk-now">
              <p className="sk-mini">At checkout</p>
              <Row k="House Medium Roast, 12 oz" v="" className="is-plain" />
              <Target fx={fx} className="sk-pricebox">
                <span>Item price</span>
                <b>$17.50</b>
              </Target>
              <Row k="Total" v="$17.50" className="is-total" />
              <span className="sk-btn">Complete purchase</span>
            </div>
          </div>
        </div>
      );
    case "verify":
      return (
        <div className="sk sk-ch">
          <Bar domain={scene.domain} />
          <div className="sk-behind" aria-hidden="true">
            <div className="sk-head">
              <img className="sk-logo" src="/skins/chargehub.svg" alt="" />
              <span className="sk-word">Chargehub</span>
            </div>
            <span className="sk-ghost" />
            <span className="sk-ghost is-short" />
            <span className="sk-ghost" />
          </div>
          <Target fx={fx} className="sk-modal">
            <div className="sk-modal-h">
              <img className="sk-logo" src="/skins/chargehub-verify.svg" alt="" />
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
            <span className="sk-btn">Verify and continue</span>
          </Target>
        </div>
      );
    case "sub":
      return (
        <div className="sk sk-sn">
          <Bar domain={scene.domain} />
          <div className="sk-head">
            <span className="sk-mark">
              <i />
              <i />
              <i />
              <i />
            </span>
            <span className="sk-word">soundnest</span>
            <span className="sk-step">Checkout</span>
          </div>
          <div className="sk-body">
            <div className="sk-item">
              <span className="sk-thumb sk-thumb-phones" />
              <div>
                <p className="sk-name">Studio headphones, closed-back</p>
                <p className="sk-pill">One-time purchase</p>
              </div>
              <b>$59.00</b>
            </div>
            <Row k="Total due today" v="$59.00" className="is-total" />
            <span className="sk-btn">Pay $59.00</span>
            <Target fx={fx} className="sk-fine">
              By placing this order you start Soundnest Plus: $9.99/month after 30 days. Renews automatically until cancelled.
            </Target>
          </div>
        </div>
      );
    default:
      return (
        <div className="sk sk-vm">
          <Bar domain={scene.domain} />
          <div className="sk-head">
            <span className="sk-bolt" />
            <span className="sk-word">Voltmart</span>
          </div>
          <Target fx={fx} className="sk-body sk-calm">
            <p className="sk-h">Checkout</p>
            <Row k="USB-C cable, 2 m" v="$24.00" />
            <Row k="Standard shipping (shown on product page)" v="$4.00" />
            <Row k="Total" v="$28.00" className="is-total" />
            <span className="sk-btn">Pay $28.00</span>
          </Target>
        </div>
      );
  }
}

function Page({ scene, t, n }: { scene: ScanScene; t: number; n: number }) {
  const block = scene.verdict === "block";
  const scan = easeOut(seg(t, 0.04, 0.34));
  const cursor = easeOut(seg(t, 0.08, 0.38));
  const snap = back(seg(t, 0.38, 0.5));
  const x1 = easeOut(seg(t, 0.48, 0.56));
  const x2 = easeOut(seg(t, 0.53, 0.61));
  const stamp = seg(t, 0.64, 0.72);
  // Tag lands: drops in on its string and swings to rest.
  const swing = stamp < 1 ? -18 + 14 * back(stamp) : -4;
  const recoil = block ? easeOut(seg(t, 0.46, 0.56)) : 0;
  const off = (1 - snap) * 34;
  const tone = block ? "red" : "pass";
  const fx: Fx = { block, snap, x1, x2, off };
  const verdict = stamp > 0 ? (block ? "Held" : "Cleared") : t > 0.02 ? "Scanning" : "Queued";
  return (
    <div className={`ts-page ts-${tone} ts-sk-${scene.id}`}>
      <div className="ts-form">
        <div className="ts-form-row">
          <p className="ts-form-t">Lane B · PayCheck</p>
          <span className="illus-tag">Illustration</span>
        </div>
        <dl className="ts-meta">
          <div>
            <dt>01 Store</dt>
            <dd>{scene.store}</dd>
          </div>
          <div>
            <dt>02 Inspection</dt>
            <dd>{String(n).padStart(2, "0")} of {SCENES.length}</dd>
          </div>
          <div>
            <dt>03 Verdict</dt>
            <dd className={verdict === "Held" ? "is-held" : undefined}>{verdict}</dd>
          </div>
        </dl>
      </div>
      <div className="ts-doc">
        <div className="ts-content">
          <Content scene={scene} fx={fx} />
        </div>
        {/* The x-ray covers the page while the scan passes, then lifts once the bracket lands so each store's own skin shows. */}
        <div className="ts-xray" style={{ clipPath: `inset(0 0 ${(100 - scan * 100).toFixed(2)}% 0)`, opacity: 1 - seg(t, 0.4, 0.5) }}>
          <div className="ts-content">
            <Content scene={scene} fx={fx} />
          </div>
        </div>
        <span className="ts-scan" style={{ top: `${scan * 100}%`, opacity: t > 0.02 && t < 0.36 ? 1 : 0 }} />
        <svg
          className="ts-cursor"
          viewBox="0 0 24 24"
          style={{
            left: `${92 - cursor * 40 + recoil * 14}%`,
            top: `${96 - cursor * 52 + recoil * 20}%`,
            opacity: t < 0.06 ? 0 : 1 - recoil,
          }}
        >
          <path d="M3 2 L20 12 L12.5 13.6 L9 21 Z" />
        </svg>
        <span className="ts-tag-anchor">
          <Tag
            verdict={block ? "held" : "cleared"}
            className="ts-stamp"
            label={`${block ? "✕ Blocked · " : "✓ Allowed · "}${scene.label}`}
            detail={scene.why}
            style={{ opacity: stamp > 0 ? Math.min(1, stamp * 3) : 0, transform: `translateY(${(1 - Math.min(1, stamp * 2)) * -14}px) rotate(${swing}deg)` }}
          />
        </span>
      </div>
    </div>
  );
}

export function TrickScan({ progress }: { progress: MotionValue<number> | null }) {
  const reduced = usePrefersReducedMotion();
  const [t, ref] = useDriver(progress, SCENES.length * 3400, 1);
  if (reduced) {
    return (
      <div className="ts ts-still" aria-hidden="true">
        {SCENES.map((scene) => (
          <Page key={scene.label} scene={scene} t={1} n={SCENES.indexOf(scene) + 1} />
        ))}
      </div>
    );
  }
  const pos = Math.min(SCENES.length - 1e-6, t * SCENES.length);
  const index = Math.floor(pos);
  const local = pos - index;
  // Hand-off between scenes: the page slides out left and the next slides in.
  const out = seg(local, 0.9, 1);
  return (
    <div ref={ref} className="ts" aria-hidden="true">
      <ol className="ts-rail">
        {SCENES.map((scene, i) => (
          <li key={scene.label} data-state={i < index ? "done" : i === index ? "on" : "off"} data-tone={scene.verdict === "block" ? "red" : "pass"}>
            <span />
            <em>{String(i + 1).padStart(2, "0")}</em>
            {scene.label}
          </li>
        ))}
      </ol>
      <div className="ts-frame">
        <div className="ts-slide" style={{ opacity: Math.min(index > 0 ? 0.15 + 0.85 * seg(local, 0, 0.05) : 1, 1 - out), transform: `translateX(${(index > 0 ? (1 - seg(local, 0, 0.05)) * 60 : 0) - out * 60}px)`, }}>
          <Page scene={SCENES[index]} t={Math.min(1, local / 0.9)} n={index + 1} />
        </div>
      </div>
    </div>
  );
}
