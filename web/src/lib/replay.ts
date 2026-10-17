import { seg } from "./ease";
import type { Replay, StepKind } from "./types";

export interface Visual {
  catchAt: number;
  popupAt: number;
  productAt: number;
  paidAt: number;
  clickAt: number;
  /** 0..1 dim of the guarded page. 1 means the page is down to 28% (overlay at 0.72). */
  dim: number;
  /** 0..1 bracket slide-in. */
  bracket: number;
  /** 0..1 red → near-white crossfade, starting 1,200 ms after the catch. */
  settle: number;
  /** 0..1 catch glow. */
  glow: number;
  msShown: number;
  /** 0..1 latency count, 400 ms from the catch. */
  count: number;
  /** Milliseconds after payment. Receipt lines print 120 ms apart. */
  sincePaid: number;
  /** 0..1 copycat letter flip, 400 ms from the catch. */
  letterFlip: number;
  /** Bracket around the flipped characters, after the flip. */
  letterBracket: number;
  showReadout: boolean;
  evidence: number;
  steer: number;
  lineFill: number;
  totalFill: number;
  popup: number;
  product: number;
  search: number;
  showCursor: boolean;
  cursor: number;
  pressing: boolean;
  clicked: boolean;
}

function at(replay: Replay, kind: StepKind): number | undefined {
  return replay.steps.find((step) => step.kind === kind)?.t_ms;
}

export function visualAt(t: number, replay: Replay, reduced: boolean): Visual {
  const catchAt = at(replay, "catch") ?? 0;
  const popupAt = at(replay, "popup") ?? 0;
  const productAt = at(replay, "product") ?? 0;
  const paidAt = at(replay, "paid") ?? replay.duration_ms;
  const clickAt = at(replay, "click") ?? popupAt + 3800;
  const latency = replay.verdict.latency_ms;
  const end = reduced || t >= replay.duration_ms - 1;

  if (end) {
    return {
      catchAt,
      popupAt,
      productAt,
      paidAt,
      clickAt,
      dim: 0,
      bracket: 1,
      settle: 1,
      glow: 0,
      msShown: latency ?? 0,
      count: 1,
      sincePaid: 100_000,
      letterFlip: 1,
      letterBracket: 1,
      showReadout: true,
      evidence: 1,
      steer: 1,
      lineFill: 1,
      totalFill: 1,
      popup: 1,
      product: 0,
      search: 0,
      showCursor: false,
      cursor: 1,
      pressing: false,
      clicked: true,
    };
  }

  const dimIn = seg(t, catchAt, 400);
  const dimOut = seg(t, catchAt + 1100, 500);
  const bracket = seg(t, catchAt, 400);
  const settle = seg(t, catchAt + 900, 500);

  return {
    catchAt,
    popupAt,
    productAt,
    paidAt,
    clickAt,
    dim: dimIn * (1 - dimOut),
    bracket,
    settle,
    glow: bracket * (1 - settle),
    msShown: t < catchAt ? 0 : (latency ?? 0),
    count: t < catchAt ? 0 : 1,
    sincePaid: Math.max(0, t - paidAt),
    letterFlip: seg(t, catchAt, 400),
    letterBracket: seg(t, catchAt + 400, 200),
    showReadout: t >= catchAt,
    evidence: seg(t, catchAt + 600, 600),
    steer: seg(t, catchAt + 1000, 600),
    lineFill: seg(t, paidAt, 600),
    totalFill: seg(t, paidAt + 300, 600),
    popup: seg(t, popupAt, 600),
    product: seg(t, productAt, 600) * (1 - seg(t, popupAt, 600)),
    search: 1 - seg(t, productAt, 600),
    showCursor: t >= popupAt + 200 && t < clickAt + 700,
    cursor: seg(t, popupAt + 400, 2800),
    pressing: t >= clickAt && t < clickAt + 180,
    clicked: t >= clickAt,
  };
}
