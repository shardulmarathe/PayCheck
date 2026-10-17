import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { EASE, mixHex } from "../lib/ease";
import { clock, formatUsd } from "../lib/format";
import { visualAt, type Visual } from "../lib/replay";
import type { CartScene, LaneCopy, Replay, ScamScene } from "../lib/types";
import { usePrefersReducedMotion, useReplay } from "../hooks/useReplay";
import { ExampleMark } from "./Chrome";

function PlayIcon() {
  return (
    <svg width="12" height="14" viewBox="0 0 12 14" aria-hidden="true">
      <path d="M1 1.2 L11 7 L1 12.8 Z" fill="currentColor" />
    </svg>
  );
}

function PauseIcon() {
  return (
    <svg width="12" height="14" viewBox="0 0 12 14" aria-hidden="true">
      <path d="M1 1 H4 V13 H1 Z M8 1 H11 V13 H8 Z" fill="currentColor" />
    </svg>
  );
}

function Cursor() {
  return (
    <svg className="cursor" viewBox="0 0 16 20" aria-hidden="true">
      <path d="M1 1 L1 16 L5.2 12.2 L8.4 18 L10.6 17 L7.4 11.2 L13 11 Z" fill="#EEF1F5" stroke="#0A0C0F" strokeWidth="1" />
    </svg>
  );
}

function CornerFrame({ progress, settle, glow, dashed }: { progress: number; settle: number; glow: number; dashed: boolean }) {
  if (progress <= 0.01) return null;
  const color = mixHex("#FF453A", "#EEF1F5", settle);
  const out = (1 - progress) * 12;
  const filter = glow > 0.02 ? `drop-shadow(0 0 8px rgb(255 69 58 / ${0.45 * glow}))` : undefined;
  const dash = dashed ? "3 2" : undefined;
  const corners = [
    { key: "tl", style: { top: -out, left: -out }, d: "M13 1 H1 V13" },
    { key: "tr", style: { top: -out, right: -out }, d: "M1 1 H13 V13" },
    { key: "bl", style: { bottom: -out, left: -out }, d: "M13 13 H1 V1" },
    { key: "br", style: { bottom: -out, right: -out }, d: "M1 13 H13 V1" },
  ];
  return (
    <div className="corners" aria-hidden="true" style={{ filter }}>
      {corners.map((corner) => (
        <svg key={corner.key} className="corner" style={corner.style} viewBox="0 0 14 14">
          <path d={corner.d} fill="none" stroke={color} strokeWidth="1.5" strokeDasharray={dash} />
        </svg>
      ))}
    </div>
  );
}

function Readout({ visual, latency, label }: { visual: Visual; latency: number; label: string }) {
  if (!visual.showReadout && visual.settle <= 0) return null;
  const color = mixHex("#FF453A", "#9AA3AE", visual.settle);
  return (
    <p className="readout" style={{ opacity: visual.showReadout ? 1 : 0, color }} aria-hidden="true">
      <span className="readout-hot" style={{ opacity: 1 - visual.settle }}>
        <span
          className="readout-ms"
          style={{ textShadow: visual.glow > 0.05 ? `0 0 8px rgb(255 69 58 / ${0.45 * visual.glow})` : undefined }}
        >
          {visual.msShown} ms
        </span>
        <span className="label" style={{ color: "inherit" }}>
          {label}
        </span>
      </span>
      <span className="readout-quiet label" style={{ opacity: visual.settle, color: "var(--text-2)" }}>
        Blocked · {latency} ms
      </span>
    </p>
  );
}

function DamageText({ text, fill }: { text: string; fill: number }) {
  return (
    <span className="damage-text">
      <span>{text}</span>
      <span className="on-fill" style={{ clipPath: `inset(0 ${Math.max(0, 100 - fill * 100)}% 0 0)` }}>
        {text}
      </span>
    </span>
  );
}

function Receipt({ lane, visual }: { lane: LaneCopy; visual: Visual }) {
  const lost = lane.outcome === "lost";
  const lineFill = lost ? visual.lineFill : 0;
  const totalFill = lost ? visual.totalFill : 0;
  return (
    <div className="receipt">
      {lane.lines.map((line) => {
        const fill = line.damage ? lineFill : 0;
        return (
          <div key={line.label} className={line.muted ? "receipt-row muted" : "receipt-row"}>
            {line.damage ? <span className="receipt-fill" style={{ transform: `scaleX(${fill})` }} /> : null}
            {line.damage ? <DamageText text={line.label} fill={fill} /> : <span>{line.label}</span>}
            {line.damage ? <DamageText text={formatUsd(line.amount)} fill={fill} /> : <span>{formatUsd(line.amount)}</span>}
          </div>
        );
      })}
      <div className="paid-row">
        <p className="label">{lane.paid_label}</p>
        <div className="paid-num-wrap">
          {lost ? <span className="paid-fill" style={{ transform: `scaleX(${totalFill})` }} /> : null}
          <span className="paid-num">
            {lost ? <DamageText text={formatUsd(lane.paid)} fill={totalFill} /> : formatUsd(lane.paid)}
          </span>
        </div>
      </div>
      <p className={lost ? "micro paid-note loss" : "micro paid-note"} style={{ opacity: lost ? Math.max(totalFill, 0.001) : 1 }}>
        {lane.paid_note}
      </p>
    </div>
  );
}

function CartView({ scene, visual, lane }: { scene: CartScene; visual: Visual; lane: "without" | "with" }) {
  const guarded = lane === "with";
  const dim = guarded ? visual.dim : 0;
  return (
    <div className="store" style={{ ["--dim" as string]: String(dim) }} aria-hidden="true">
      <div className="view" style={{ opacity: visual.search }}>
        <p className="search-query">{scene.search_query}</p>
        <div className="search-hit dimmable">
          <div className="tile sm">{scene.product_mark}</div>
          <div>
            <p className="product-title">{scene.product_title}</p>
            <p className="product-price">{scene.product_price}</p>
          </div>
        </div>
      </div>
      <div className="view" style={{ opacity: visual.product }}>
        <div className="product-row dimmable">
          <div className="tile">{scene.product_mark}</div>
          <div>
            <p className="product-title">{scene.product_title}</p>
            <p className="product-price">{scene.product_price}</p>
            <p className="inworld">In stock</p>
          </div>
        </div>
      </div>
      <div className="view" style={{ opacity: visual.popup }}>
        <div className="product-row dimmable">
          <div className="tile">{scene.product_mark}</div>
          <div>
            <p className="product-title">{scene.product_title}</p>
            <p className="product-price">{scene.product_price}</p>
            <p className="inworld">{scene.qty_label}</p>
          </div>
          <div className="cart-box">
            <p className="inworld">{scene.cart_label}</p>
            <p className="cart-total">{scene.cart_total}</p>
            <p className="inworld">{scene.cart_note}</p>
          </div>
        </div>
        <div className="popup" style={{ opacity: visual.popup }}>
          <div className="popup-main dimmable">
            <p className="popup-title">{scene.popup_title}</p>
            <p className="popup-body">{scene.popup_body}</p>
            <div className="popup-actions">
              <span className={visual.pressing && !guarded ? "continue pressed" : "continue"}>{scene.popup_primary}</span>
              <span className={guarded && visual.settle > 0.5 ? "dismiss chosen" : "dismiss"}>{scene.popup_dismiss}</span>
            </div>
          </div>
          <div className="fine-wrap">
            {guarded ? (
              <CornerFrame progress={visual.bracket} settle={visual.settle} glow={visual.glow} dashed={false} />
            ) : null}
            <p className="fine-print">{scene.popup_fine_print}</p>
          </div>
        </div>
        {!guarded && visual.showCursor ? (
          <span style={{ position: "absolute", left: `${62 - visual.cursor * 34}%`, top: `${78 - visual.cursor * 22}%` }}>
            <Cursor />
          </span>
        ) : null}
      </div>
    </div>
  );
}

function Lane({
  copy,
  scene,
  visual,
  side,
  latency,
  readout,
}: {
  copy: LaneCopy;
  scene: CartScene;
  visual: Visual;
  side: "without" | "with";
  latency: number;
  readout: string;
}) {
  const reveal = side === "with" ? visual.evidence : visual.lineFill;
  const steer = side === "with" ? visual.steer : visual.totalFill;
  return (
    <article className="lane">
      <div className="lane-kicker">
        <p className={side === "with" ? "label on" : "label"}>{copy.kicker}</p>
        <p className="micro">Shopper · Haiku via Browser Use</p>
      </div>
      <div className="browser">
        <div className="chrome">
          <span className="dots" aria-hidden="true">
            <i />
            <i />
            <i />
          </span>
          <span className="url-pill">
            {visual.popup > 0.5 ? scene.cart_url : visual.product > 0.5 ? scene.product_url : scene.search_url}
          </span>
        </div>
        <CartView scene={scene} visual={visual} lane={side} />
        {side === "with" ? (
          <Readout visual={{ ...visual, showReadout: visual.showReadout && visual.popup > 0.4 }} latency={latency} label={readout} />
        ) : null}
      </div>
      <div className="story" style={{ opacity: Math.max(reveal, side === "with" ? visual.settle : visual.totalFill) }}>
        <p className={side === "with" ? "label on" : "label"}>{copy.story_label}</p>
        <p className={side === "with" ? "body quote" : "body"} style={{ opacity: reveal }}>
          {copy.story_body}
        </p>
        <p className={side === "with" ? "title" : "title muted"} style={{ opacity: steer }}>
          {copy.story_title}
        </p>
      </div>
      <Receipt lane={copy} visual={visual} />
    </article>
  );
}

function ScamBody({ scene, visual, latency, readout }: { scene: ScamScene; visual: Visual; latency: number; readout: string }) {
  const onVerify = visual.popup > 0.35 || visual.settle > 0;
  const prefix = onVerify ? scene.verify_url_prefix : scene.product_url_prefix;
  const suffix = onVerify ? scene.verify_url_suffix : scene.product_url_suffix;
  const flag = onVerify ? scene.verify_url_flag : scene.product_url_flag;
  return (
    <div className="browser scam" style={{ ["--dim" as string]: String(visual.dim) }}>
      <div className="chrome">
        <span className="dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span className="url-slot">
          <CornerFrame progress={visual.bracket} settle={visual.settle} glow={visual.glow} dashed />
          <span className="url-pill">
            <span>
              {prefix}
              <span className="flag">{flag}</span>
              {suffix}
            </span>
          </span>
        </span>
        <Readout visual={visual} latency={latency} label={readout} />
      </div>
      <div className="scam-page dimmable" aria-hidden="true">
        {onVerify ? (
          <>
            <div>
              <p className="scam-brand">{scene.brand}</p>
              <p className="scam-headline">{scene.headline}</p>
              <p className="body" style={{ marginTop: 8 }}>
                {scene.body}
              </p>
              <div className="scam-fields">
                {scene.fields.map((field) => (
                  <div key={field} className={field === "Card number" ? "field" : "field short"}>
                    <span className="micro">{field}</span>
                    <i />
                  </div>
                ))}
              </div>
            </div>
            <div className="order-card">
              <p className="micro">{scene.order_label}</p>
              <div className="order-line">
                <span>{scene.order_item}</span>
                <span className="num">{scene.order_price}</span>
              </div>
            </div>
          </>
        ) : (
          <div className="product-row">
            <div className="tile">USB</div>
            <div>
              <p className="scam-brand">{scene.brand}</p>
              <p className="product-title">{scene.product_name}</p>
              <p className="product-price">{scene.product_price}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Timeline({
  replay,
  t,
  playing,
  onToggle,
  onSeek,
  onPause,
  textControl = false,
}: {
  replay: Replay;
  t: number;
  playing: boolean;
  onToggle: () => void;
  onSeek: (ms: number) => void;
  onPause: () => void;
  /** Hero replay: mono word, no icon box. */
  textControl?: boolean;
}) {
  const duration = replay.duration_ms;
  const ticks = replay.steps.filter((step) => step.tick);
  const seekFrom = (clientX: number, width: number, left: number) => {
    const ratio = Math.min(1, Math.max(0, (clientX - left) / width));
    onPause();
    onSeek(ratio * duration);
  };
  return (
    <div className="timeline">
      <div className="timeline-controls">
        <button
          type="button"
          className={textControl ? "play play-text" : "play"}
          aria-label={playing ? "Pause replay" : "Play replay"}
          onClick={onToggle}
        >
          {textControl ? (playing ? "Pause" : "Play") : playing ? <PauseIcon /> : <PlayIcon />}
        </button>
        <p className="time">
          {clock(t)} / {clock(duration)}
        </p>
        <div
          className="track"
          role="slider"
          tabIndex={0}
          aria-label="Replay timeline"
          aria-valuemin={0}
          aria-valuemax={duration}
          aria-valuenow={Math.round(t)}
          aria-valuetext={`${clock(t)} of ${clock(duration)}`}
          onKeyDown={(event) => {
            const step = event.shiftKey ? 5000 : 1000;
            if (event.key === "ArrowRight") {
              event.preventDefault();
              onPause();
              onSeek(t + step);
            } else if (event.key === "ArrowLeft") {
              event.preventDefault();
              onPause();
              onSeek(t - step);
            } else if (event.key === "Home") {
              event.preventDefault();
              onPause();
              onSeek(0);
            } else if (event.key === "End") {
              event.preventDefault();
              onPause();
              onSeek(duration);
            } else if (event.key === " " || event.key === "Enter") {
              event.preventDefault();
              onToggle();
            }
          }}
          onPointerDown={(event) => {
            event.currentTarget.setPointerCapture(event.pointerId);
            const rect = event.currentTarget.getBoundingClientRect();
            seekFrom(event.clientX, rect.width, rect.left);
          }}
          onPointerMove={(event) => {
            if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
            const rect = event.currentTarget.getBoundingClientRect();
            seekFrom(event.clientX, rect.width, rect.left);
          }}
        >
          <span className="track-line" />
          <span className="track-fill" style={{ width: `${(t / duration) * 100}%` }} />
          {ticks.map((step) =>
            step.catch ? (
              <span key={step.id} className="catch-dot" style={{ left: `${(step.t_ms / duration) * 100}%` }} />
            ) : (
              <span
                key={step.id}
                className={t >= step.t_ms ? "tick" : "tick future"}
                style={{ left: `${(step.t_ms / duration) * 100}%` }}
              />
            ),
          )}
        </div>
      </div>
      <div className="tick-labels" aria-hidden="true">
        {ticks.map((step) => (
          <span
            key={step.id}
            className={step.catch ? "micro tick-label loss" : "micro tick-label"}
            style={{ left: `${(step.t_ms / duration) * 100}%` }}
          >
            {step.catch ? `Caught · ${replay.verdict.latency_ms} ms` : step.label}
          </span>
        ))}
      </div>
      <p className="micro timeline-caption">{replay.timeline_caption}</p>
      <p className="sr-only">Space plays or pauses. Arrow keys move the playhead by one second.</p>
    </div>
  );
}

export function ReplayScene({
  replay,
  example,
  autoplay,
  entrance = false,
  tilt = false,
  label,
  textControl = false,
}: {
  replay: Replay;
  example: boolean;
  autoplay: "mount" | "view";
  entrance?: boolean;
  /** Perspective pose for the side-by-side lanes. The scrubber stays flat. */
  tilt?: boolean;
  /** Replaces the data kicker. Later replays on the Demo tab use Replay 2, Replay 3, … */
  label?: string;
  /** Mono Play / Pause word for the landing replay. */
  textControl?: boolean;
}) {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(autoplay === "mount");
  useEffect(() => {
    if (autoplay !== "view" || !ref.current) return;
    const node = ref.current;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setSeen(true);
      },
      { threshold: 0.35 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [autoplay]);
  const clockState = useReplay(replay.duration_ms, seen);
  const visual = visualAt(clockState.t, replay, clockState.reduced);
  const [announced, setAnnounced] = useState("");
  useEffect(() => {
    if (visual.settle > 0.85) {
      setAnnounced(`Blocked. ${replay.verdict.latency_ms} milliseconds. ${replay.verdict.steer}`);
    }
  }, [visual.settle, replay.verdict.latency_ms, replay.verdict.steer]);

  return (
    <section className="section" ref={ref} aria-labelledby={`replay-${replay.id}`}>
      <header className="section-head">
        <div>
          <p className="label">{label ?? replay.kicker}</p>
          <h3 className="h3" id={`replay-${replay.id}`}>
            {replay.title}
          </h3>
        </div>
        <div className="section-side">
          <ExampleMark show={example} />
          <p className="label">{replay.meta_right}</p>
        </div>
      </header>
      <p className="sr-only" aria-live="polite">
        {announced}
      </p>
      {replay.scene === "upsell" ? (
        <div className={tilt ? "replay-tilt" : undefined}>
        <div className={tilt ? "replay-tilt-plane" : undefined}>
        <motion.div
          className="lanes"
          initial={entrance && !reduced ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={{ duration: entrance && !reduced ? 0.9 : 0, delay: entrance && !reduced ? 0.2 : 0, ease: EASE }}
        >
          <Lane
            copy={replay.without}
            scene={replay.scene_view}
            visual={visual}
            side="without"
            latency={replay.verdict.latency_ms}
            readout={replay.verdict.readout}
          />
          <Lane
            copy={replay.with}
            scene={replay.scene_view}
            visual={visual}
            side="with"
            latency={replay.verdict.latency_ms}
            readout={replay.verdict.readout}
          />
        </motion.div>
        </div>
        </div>
      ) : (
        <>
          <ScamBody
            scene={replay.scene_view}
            visual={visual}
            latency={replay.verdict.latency_ms}
            readout={replay.verdict.readout}
          />
          <div className="scam-cols" style={{ opacity: Math.max(visual.evidence, visual.settle) }}>
            <div>
              <p className="label">{replay.columns.flagged_label}</p>
              <p className="flagged-domain">
                {replay.scene_view.flagged_prefix}
                <span className="flag">{replay.scene_view.flagged_mark}</span>
                {replay.scene_view.flagged_suffix}
              </p>
              <p className="num muted">{replay.scene_view.flagged_real}</p>
            </div>
            <div>
              <p className="label">{replay.columns.trick_label}</p>
              <p className="body" style={{ marginTop: 8 }}>
                {replay.scene_view.trick_body}
              </p>
            </div>
            <div style={{ opacity: visual.steer }}>
              <p className="label on">{replay.columns.steer_label}</p>
              <p className="title">{replay.verdict.steer}</p>
            </div>
          </div>
        </>
      )}
      <Timeline
        replay={replay}
        t={clockState.t}
        playing={clockState.playing}
        onToggle={clockState.toggle}
        onSeek={clockState.seek}
        onPause={clockState.pause}
        textControl={textControl}
      />
    </section>
  );
}
