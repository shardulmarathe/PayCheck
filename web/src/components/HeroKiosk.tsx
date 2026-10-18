import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { HERO_CLIP, SITE } from "../lib/copy";
import { easeInOutCubic } from "../lib/motion";
import { useIntroPhase } from "./motion/Intro";
import { kioskPose, markKioskReady } from "./kioskPose";

const loadCanvas = () => import("./KioskZoomCanvas");
const KioskZoomCanvas = lazy(loadCanvas);

/** Camera dolly from the whole kiosk to its screen. */
const ZOOM_MS = 1900;
/**
 * Replay clock (seconds, hero-loop-fakecard-clean). 0–0.3 checkout page, then the fake card-check form in both panes,
 * from 7.0 the panes dim for the outcome (the clip's own burned-in outcome text was cut; these overlays replace it).
 * Outcomes are the real runs: t-fake-verify_unguarded_000 (card details entered, exposed) and
 * t-fake-verify_guarded_002 (guard block, fake_card_verification; card details never sent).
 */
const FORM_AT = 0.3;
const RESULT_AT = 7.05;

type Phase = "checkout" | "form" | "result";

function webglOk(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function HeroKiosk() {
  const reduced = usePrefersReducedMotion();
  const phase = useIntroPhase();
  const overlay = useRef<HTMLDivElement>(null);
  const device = useRef<HTMLDivElement>(null);
  const video = useRef<HTMLVideoElement>(null);
  const [webgl] = useState(webglOk);
  const [lost, setLost] = useState(false);
  const [ready, setReady] = useState(false);
  const [arrived, setArrived] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [phase2, setPhase2] = useState<Phase>("checkout");
  const zoomStarted = useRef(false);
  const zoomFrame = useRef(0);
  const flat = !webgl || lost;
  // The zoom waits for the intro's lock-on; on a repeat visit (intro skipped) it plays as soon as the kiosk is drawn.
  const zoomGo = phase === "catch" || phase === "pullback" || phase === "done";

  // Start pulled back on every visit, so the dolly-in always plays once the 3D kiosk is actually on screen.
  const [initialised] = useState(() => {
    if (!flat && !reduced) {
      kioskPose.zoom = 0;
      kioskPose.bezelHidden = false;
    } else {
      kioskPose.zoom = 1;
    }
    kioskPose.ready = false;
    return true;
  });
  void initialised;

  useEffect(() => {
    if (flat) {
      setReady(true);
      markKioskReady();
    }
  }, [flat]);

  useEffect(() => {
    if (!ready || !zoomGo || zoomStarted.current) return;
    zoomStarted.current = true;
    if (flat) {
      setArrived(true);
      return;
    }
    if (reduced) {
      kioskPose.zoom = 1;
      kioskPose.invalidate();
      return;
    }
    const t0 = performance.now();
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / ZOOM_MS);
      kioskPose.zoom = easeInOutCubic(p);
      kioskPose.invalidate();
      if (p < 1) zoomFrame.current = requestAnimationFrame(tick);
    };
    zoomFrame.current = requestAnimationFrame(tick);
  }, [ready, zoomGo, flat, reduced]);

  useEffect(
    () => () => {
      cancelAnimationFrame(zoomFrame.current);
      zoomStarted.current = false;
    },
    [],
  );

  useEffect(() => {
    if (reduced || !video.current) return;
    if (arrived) void video.current.play().catch(() => {});
  }, [arrived, reduced]);

  useEffect(() => {
    if (!arrived || flat) return;
    const timer = window.setTimeout(
      () => {
        // Keep the 3D bezel: its side and top faces give the end pose its depth behind the HTML frame.
        kioskPose.bezelHidden = false;
        kioskPose.invalidate();
      },
      reduced ? 0 : 650,
    );
    return () => window.clearTimeout(timer);
  }, [arrived, reduced, flat]);

  // Follow the replay clock for the lock-on overlay (cheap: one state change per phase).
  useEffect(() => {
    const el = video.current;
    if (!el) return;
    let frame = 0;
    const read = () => {
      const t = el.currentTime;
      const next: Phase = t >= RESULT_AT ? "result" : t >= FORM_AT ? "form" : "checkout";
      setPhase2((prev) => (prev === next ? prev : next));
      if (!el.paused) frame = requestAnimationFrame(read);
    };
    const start = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(read);
    };
    el.addEventListener("play", start);
    el.addEventListener("seeked", start);
    el.addEventListener("pause", read);
    return () => {
      cancelAnimationFrame(frame);
      el.removeEventListener("play", start);
      el.removeEventListener("seeked", start);
      el.removeEventListener("pause", read);
    };
  }, []);

  const toggle = () => {
    const el = video.current;
    if (!el) return;
    if (el.paused) void el.play().catch(() => {});
    else el.pause();
  };

  const stageClass = ["kz-stage", flat ? "is-flat" : "", flat && arrived ? "is-arrived" : "", ready ? "is-ready" : ""]
    .filter(Boolean)
    .join(" ");

  return (
    <figure className="kz">
      <div className={stageClass} data-trick-line>
        {flat ? (
          <div className="kz-stand" aria-hidden="true">
            <i />
            <i />
          </div>
        ) : (
          <Suspense fallback={null}>
            <KioskZoomCanvas
              poster={HERO_CLIP.poster}
              overlayRef={overlay}
              deviceRef={device}
              onArrive={() => setArrived(true)}
              onLost={() => setLost(true)}
              onReady={() => {
                setReady(true);
                markKioskReady();
              }}
            />
          </Suspense>
        )}
        <div ref={device} className="kz-device" data-on={flat ? "1" : "0"}>
          <p className="kz-trick">{SITE.heroTrickLine}</p>
        </div>
        <div ref={overlay} className="kz-screen" data-on={flat ? "1" : "0"}>
          <video
            ref={video}
            poster={HERO_CLIP.poster}
            muted
            loop
            playsInline
            preload="metadata"
            aria-label={SITE.heroClipCaption}
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
          >
            <source src={HERO_CLIP.webm} type="video/webm" />
            <source src={HERO_CLIP.mp4} type="video/mp4" />
          </video>
          <div className="kz-story" data-phase={reduced ? "result" : phase2} aria-hidden="true">
            {[0, 1].map((pane) => (
              <div key={pane} className={pane ? "kz-pane is-guard" : "kz-pane"}>
                <span className="kz-form">
                  <i />
                  <i />
                  <i />
                  <i />
                </span>
                {pane ? (
                  <>
                    <svg className="kz-x">
                      <line x1="6%" y1="10%" x2="94%" y2="90%" pathLength="1" />
                      <line x1="94%" y1="10%" x2="6%" y2="90%" pathLength="1" />
                    </svg>
                    <p className="kz-out is-blocked cp-tag is-held">
                      <i className="cp-tag-string" />
                      <span className="cp-tag-body">
                        <i className="cp-tag-hole" />
                        <em className="cp-tag-verdict">HELD</em>
                        <b>{SITE.heroOutcomeGuarded}</b>
                        <span>{SITE.heroOutcomeGuardedReason}</span>
                      </span>
                    </p>
                  </>
                ) : (
                  <p className="kz-out is-lost">
                    <em>Result</em>
                    <b>{SITE.heroOutcomeUnguarded}</b>
                  </p>
                )}
                <ol className="kz-steps">
                  {SITE.heroSteps.map((step, i) => (
                    <li key={step} data-n={String(i + 1).padStart(2, "0")} data-on={i === ["checkout", "form", "result"].indexOf(reduced ? "result" : phase2) ? "1" : "0"}>
                      {step}
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </div>
          {reduced ? (
            <button type="button" className="kz-play" onClick={toggle} aria-label={playing ? "Pause replay" : "Play replay"}>
              <span aria-hidden="true">{playing ? "❚❚" : "▶"}</span>
              {playing ? "Pause" : "Play"}
            </button>
          ) : null}
        </div>
      </div>
      <figcaption className="sr-only">
        {SITE.heroTrickLine} {SITE.heroClipCaption}
      </figcaption>
    </figure>
  );
}
