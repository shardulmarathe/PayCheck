import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, RefObject } from "react";
import { usePrefersReducedMotion, useReplay } from "../hooks/useReplay";
import type { ReplayChoice } from "../hooks/useRoute";
import { easeOut, mixHex } from "../lib/ease";
import { clock, formatLatency, formatLatencyCount, formatUsd } from "../lib/format";
import { visualAt, type Visual } from "../lib/replay";
import type { CartScene, LaneCopy, Replay } from "../lib/types";

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

function Readout({
  visual,
  latency,
  example,
  category,
  inline,
}: {
  visual: Visual;
  latency: number | null;
  example: boolean;
  category: string;
  inline?: boolean;
}) {
  if (!visual.showReadout && visual.settle <= 0) return null;
  const color = mixHex("#FF453A", "#9AA3AE", visual.settle);
  return (
    <p className={inline ? "readout inline" : "readout"} style={{ color }} aria-hidden="true">
      <span style={{ textShadow: visual.glow > 0.05 ? `0 0 8px rgb(255 69 58 / ${0.45 * visual.glow})` : undefined }}>
        {formatLatencyCount(latency, visual.count, example)} · Blocked · {category}
      </span>
    </p>
  );
}

function Receipt({ lane, visual }: { lane: LaneCopy; visual: Visual }) {
  const lost = lane.outcome === "lost";
  const since = visual.sincePaid;
  const damageIndex = lane.lines.findIndex((line) => line.damage);
  const rollStart = (damageIndex >= 0 ? damageIndex : lane.lines.length) * 120 + (damageIndex >= 0 ? 600 : 0);
  const roll = lost ? Math.min(1, Math.max(0, (since - rollStart) / 600)) : 1;
  const base = lane.lines.filter((line) => !line.damage).reduce((sum, line) => sum + line.amount, 0);
  const shownTotal = lost ? base + (lane.paid - base) * easeOut(roll) : lane.paid;
  const totalIn = since >= lane.lines.length * 120;
  return (
    <div className="receipt receipt-v3">
      {lane.lines.map((line, index) => {
        if (since < index * 120) return null;
        const fill = line.damage ? Math.min(1, Math.max(0, (since - index * 120) / 600)) : 0;
        return (
          <div key={line.label} className={line.muted ? "receipt-row muted" : "receipt-row"}>
            {line.damage ? <span className="receipt-fill" style={{ transform: `scaleX(${fill})` }} /> : null}
            <span className={line.damage ? "on-line" : undefined} style={line.damage ? { color: fill > 0.55 ? "var(--bg)" : undefined } : undefined}>
              {line.label}
            </span>
            <span style={line.damage ? { color: fill > 0.55 ? "var(--bg)" : undefined } : undefined}>{formatUsd(line.amount)}</span>
          </div>
        );
      })}
      {totalIn ? (
        <div className="paid-block">
          <div>
            <p className="label">{lane.paid_label}</p>
            <p className={lost ? "micro paid-note loss" : "micro paid-note"}>{lane.paid_note}</p>
          </div>
          <p className={lost ? "paid-total lost" : "paid-total"} style={lost ? { opacity: Math.max(roll, 0.001) } : undefined}>
            {formatUsd(shownTotal)}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function UpsellLane({
  copy,
  scene,
  visual,
  side,
  latency,
  example,
  shopper,
  yaw,
  onReplay,
}: {
  copy: LaneCopy;
  scene: CartScene;
  visual: Visual;
  side: "without" | "with";
  latency: number | null;
  example: boolean;
  shopper: string;
  yaw: number;
  onReplay: () => void;
}) {
  const guarded = side === "with";
  const showPopup = visual.popup > 0.35 || visual.settle > 0 || visual.clicked;
  const shadow = panelShadow(yaw);
  return (
    <article className="lane">
      <div className="lane-kicker">
        <p className="label">{copy.kicker}</p>
        <p className="micro">{shopper}</p>
      </div>
      <div className="panel-slot">
        <div className="panel-yaw" style={{ transform: `rotateY(${guarded ? -yaw : yaw}deg)` }}>
          <div
            className="panel-card"
            style={{ boxShadow: shadow }}
            onClick={onReplay}
            onKeyDown={(event) => {
              if (event.key === "Enter") onReplay();
            }}
          >
            <div className="floor-shadow" />
            <div className="chrome">
              <span className="url-pill">{showPopup ? scene.cart_url : visual.product > 0.5 ? scene.product_url : scene.search_url}</span>
            </div>
            <div className="panel-body" style={{ ["--dim" as string]: guarded ? String(visual.dim) : "0" }}>
              {showPopup ? (
                <>
                  <div className="product-v3 dimmable">
                    <div className="tile">{scene.product_mark}</div>
                    <p className="product-title">{scene.product_title}</p>
                    <p className="price-side">
                      {scene.product_price} · {scene.qty_label}
                    </p>
                  </div>
                  <div className="popup flow">
                    <div className="popup-main dimmable">
                      <p className="popup-title">{scene.popup_title}</p>
                      <p className="popup-body">{scene.popup_body}</p>
                      <div className="popup-actions">
                        <span className={guarded && (visual.bracket > 0.4 || visual.settle > 0) ? "continue idle" : visual.pressing && !guarded ? "continue pressed" : "continue"}>
                          {scene.popup_primary}
                        </span>
                        <span className="dismiss">{scene.popup_dismiss}</span>
                      </div>
                    </div>
                    <div className="fine-wrap">
                      {guarded ? <CornerFrame progress={visual.bracket} settle={visual.settle} glow={visual.glow} dashed={false} /> : null}
                      <p className="fine-print">{scene.popup_fine_print}</p>
                    </div>
                  </div>
                  {!guarded && visual.clicked ? <p className="lane-note">{copy.story_body}</p> : null}
                  {guarded ? <Readout visual={visual} latency={latency} example={example} category="upsell" inline /> : null}
                  {guarded ? (
                    <p className="steer" style={{ opacity: visual.steer }}>
                      {copy.story_title}
                    </p>
                  ) : null}
                  <Receipt lane={copy} visual={visual} />
                </>
              ) : (
                <div className="product-v3">
                  <div className="tile">{scene.product_mark}</div>
                  <div>
                    <p className="product-title">{scene.product_title}</p>
                    <p className="price-side">{visual.product > 0.4 ? scene.product_price : scene.search_query}</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

function panelShadow(angle: number): string {
  const lift = angle / 8;
  const y = 24 + lift * 16;
  const blur = 48 + lift * 32;
  if (lift < 0.08) return `0 ${y}px ${blur}px rgba(0,0,0,.55)`;
  return `0 ${y}px ${blur}px rgba(0,0,0,.55), 0 ${8 * lift}px ${16 * lift}px rgba(0,0,0,.45)`;
}

function useTilt(ref: RefObject<HTMLElement | null>): number {
  const reduced = usePrefersReducedMotion();
  const [angle, setAngle] = useState(reduced ? 0 : 8);
  useEffect(() => {
    if (reduced) {
      setAngle(0);
      return;
    }
    let frame = 0;
    const update = () => {
      frame = 0;
      const node = ref.current;
      if (!node || window.innerWidth < 1200) {
        setAngle(0);
        return;
      }
      const rect = node.getBoundingClientRect();
      const center = rect.top + rect.height / 2;
      const mid = window.innerHeight / 2;
      const distance = Math.min(1, Math.max(0, Math.abs(center - mid) / mid));
      setAngle(8 * easeOut(distance));
    };
    const onScroll = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [reduced, ref]);
  return angle;
}

function Transport({
  replay,
  t,
  playing,
  onToggle,
  onSeek,
  onPause,
}: {
  replay: Replay;
  t: number;
  playing: boolean;
  onToggle: () => void;
  onSeek: (ms: number) => void;
  onPause: () => void;
}) {
  const duration = replay.duration_ms;
  return (
    <div className="replay-foot">
      <button type="button" className="play" aria-label={playing ? "Pause replay" : "Play replay"} onClick={onToggle}>
        {playing ? <PauseIcon /> : <PlayIcon />}
      </button>
      <p className="time">
        {clock(t)} / {clock(duration)}
      </p>
      <div
        className="hairline-track"
        role="slider"
        tabIndex={0}
        aria-label="Replay timeline"
        aria-valuemin={0}
        aria-valuemax={duration}
        aria-valuenow={Math.round(t)}
        aria-valuetext={`${clock(t)} of ${clock(duration)}`}
        onKeyDown={(event) => {
          const step = event.shiftKey ? 5000 : 1000;
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            event.preventDefault();
            onPause();
            onSeek(t + (event.key === "ArrowRight" ? step : -step));
          } else if (event.key === "Home" || event.key === "End") {
            event.preventDefault();
            onPause();
            onSeek(event.key === "Home" ? 0 : duration);
          } else if (event.key === " " || event.key === "Enter") {
            event.preventDefault();
            onToggle();
          }
        }}
        onPointerDown={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          onPause();
          onSeek(((event.clientX - rect.left) / rect.width) * duration);
        }}
      >
        <span className="hairline">
          <i style={{ width: `${(t / duration) * 100}%` }} />
        </span>
      </div>
      <p className="replay-caption">{replay.timeline_caption}</p>
    </div>
  );
}

export function ReplayScene({
  replay,
  example,
  choice,
  onChoice,
}: {
  replay: Replay;
  example: boolean;
  choice: ReplayChoice;
  onChoice: (next: ReplayChoice) => void;
}) {
  const reduced = usePrefersReducedMotion();
  const ref = useRef<HTMLElement>(null);
  const [seen, setSeen] = useState(false);
  const yaw = useTilt(ref);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setSeen(true);
      },
      { threshold: 0.35 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [replay.id]);
  const clockState = useReplay(replay.duration_ms, seen && !reduced);
  const visual = visualAt(clockState.t, replay, clockState.reduced);
  const [announced, setAnnounced] = useState("");
  useEffect(() => {
    if (visual.settle > 0.85) {
      setAnnounced(`Blocked. ${formatLatency(replay.verdict.latency_ms, example)}. ${replay.verdict.steer}`);
    }
  }, [visual.settle, replay.verdict.latency_ms, replay.verdict.steer, example]);

  const onKey = (event: KeyboardEvent) => {
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      onChoice(event.key === "ArrowRight" ? 2 : 1);
    }
  };

  return (
    <section className="section replay-section" ref={ref} aria-labelledby={`replay-${replay.id}`}>
      <header className="replay-head">
        <div>
          <p className="label">
            {replay.kicker}
            {example ? " · example data" : ""}
          </p>
          <h2 className="title-xl" id={`replay-${replay.id}`}>
            {replay.title}
          </h2>
        </div>
        <div className="replay-switch" role="tablist" aria-label="Replays" onKeyDown={onKey}>
          <button type="button" role="tab" aria-selected={choice === 1} className="replay-tab" onClick={() => onChoice(1)}>
            Replay 1 · Upsell
          </button>
          <button type="button" role="tab" aria-selected={choice === 2} className="replay-tab wide" onClick={() => onChoice(2)}>
            Replay 2 · Copycat store
          </button>
        </div>
      </header>
      <p className="sr-only" aria-live="polite">
        {announced}
      </p>
      {replay.scene === "upsell" ? (
        <div className="lanes">
          <UpsellLane
            copy={replay.without}
            scene={replay.scene_view}
            visual={visual}
            side="without"
            latency={replay.verdict.latency_ms}
            example={example}
            shopper={replay.shopper}
            yaw={yaw}
            onReplay={clockState.restart}
          />
          <UpsellLane
            copy={replay.with}
            scene={replay.scene_view}
            visual={visual}
            side="with"
            latency={replay.verdict.latency_ms}
            example={example}
            shopper={replay.shopper}
            yaw={yaw}
            onReplay={clockState.restart}
          />
        </div>
      ) : (
        <ScamView replay={replay} visual={visual} example={example} yaw={yaw} onReplay={clockState.restart} />
      )}
      <Transport
        replay={replay}
        t={clockState.t}
        playing={clockState.playing}
        onToggle={clockState.toggle}
        onSeek={clockState.seek}
        onPause={clockState.pause}
      />
    </section>
  );
}

function ScamView({
  replay,
  visual,
  example,
  yaw,
  onReplay,
}: {
  replay: Extract<Replay, { scene: "scam" }>;
  visual: Visual;
  example: boolean;
  yaw: number;
  onReplay: () => void;
}) {
  const scene = replay.scene_view;
  const mark = visual.letterFlip >= 0.5 ? scene.flagged_mark : (scene.flagged_from ?? "ll");
  const spin = visual.letterFlip > 0.02 && visual.letterFlip < 0.98 ? Math.sin(visual.letterFlip * Math.PI) * 70 : 0;
  return (
    <div className="replay-split">
      <div className="panel-slot">
        <div className="panel-yaw" style={{ transform: `rotateY(${yaw}deg)` }}>
          <div className="panel-card" style={{ boxShadow: panelShadow(yaw) }} onClick={onReplay}>
            <div className="floor-shadow" />
            <div className="chrome">
              <span className="url-slot">
                <CornerFrame progress={visual.bracket} settle={visual.settle} glow={visual.glow} dashed />
                <span className="url-pill">
                  {scene.verify_url_prefix}
                  <span className="flag">{scene.verify_url_flag}</span>
                  {scene.verify_url_suffix}
                </span>
              </span>
              <Readout visual={visual} latency={replay.verdict.latency_ms} example={example} category="scam, copycat domain" />
            </div>
            <div className="scam-page dimmable" style={{ ["--dim" as string]: String(visual.dim) }}>
              <div>
                <p className="scam-brand">{scene.brand}</p>
                <p className="scam-headline">{scene.headline}</p>
                <p className="scam-copy">{scene.body}</p>
                <div className="scam-fields">
                  {scene.fields.map((field) => (
                    <div key={field} className={field === "Card number" ? "field" : "field short"}>
                      <span className="micro">{field}</span>
                      <i />
                    </div>
                  ))}
                </div>
                <span className="verify-btn">{scene.submit ?? "Verify and continue"}</span>
              </div>
              <div className="order-card">
                <p className="micro">{scene.order_label}</p>
                <p className="order-item">{scene.order_item}</p>
                <p className="num">{scene.order_price}</p>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div className="scam-side">
        <p className="label">Flagged text</p>
        <p className="flagged-xl">
          {scene.flagged_prefix}
          <span className="flip-slot" style={{ transform: `rotateX(${spin}deg)` }}>
            <CornerFrame progress={visual.letterBracket} settle={visual.settle} glow={visual.glow} dashed />
            {mark}
          </span>
          {scene.flagged_suffix}
        </p>
        <p className="micro real-store">{scene.flagged_real}</p>
        <p className="label steer-kicker">Guard → shopper</p>
        <p className="steer-xl" style={{ opacity: Math.max(visual.steer, visual.letterBracket) }}>
          {replay.verdict.steer}
        </p>
      </div>
    </div>
  );
}
