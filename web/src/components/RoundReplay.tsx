import { useEffect, useMemo, useState } from "react";
import { usePrefersReducedMotion } from "../hooks/useReplay";
import { formatPct } from "../lib/format";
import type { RoundReplay as RoundLog, RoundReplayLine } from "../lib/types";
import { useNav } from "./motion/Nav";

const MAX_LINES = 6;
const ROW_MS = 120;
const HOLD_MS = 900;

function ordered(lines: RoundReplayLine[]): RoundReplayLine[] {
  return [...lines]
    .map((line, index) => ({ line, index }))
    .sort((a, b) => {
      const rank = (line: RoundReplayLine) => (line.fed_back ? 0 : line.correct ? 2 : 1);
      const delta = rank(a.line) - rank(b.line);
      return delta !== 0 ? delta : a.index - b.index;
    })
    .map((item) => item.line);
}

export function RoundReplay({ rounds }: { rounds: RoundLog[] }) {
  const playable = useMemo(() => rounds.filter((round) => round.lines.length > 0), [rounds]);
  const reduced = usePrefersReducedMotion();
  const { isGliding } = useNav();
  const settled = reduced || isGliding;
  const [cursor, setCursor] = useState(0);
  const [count, setCount] = useState(1);

  useEffect(() => {
    if (settled || playable.length === 0) return;
    const total = Math.min(MAX_LINES, ordered(playable[cursor]?.lines ?? []).length);
    const wait = count < total ? ROW_MS : HOLD_MS;
    const timer = window.setTimeout(() => {
      if (count < total) setCount((value) => value + 1);
      else {
        setCursor((value) => (value + 1) % playable.length);
        setCount(1);
      }
    }, wait);
    return () => window.clearTimeout(timer);
  }, [count, cursor, playable, settled]);

  if (playable.length === 0) return null;
  const round = playable[settled ? playable.length - 1 : cursor] ?? playable[0];
  const lines = ordered(round.lines);
  const visible = lines.slice(0, settled ? MAX_LINES : count);
  const rates = [
    round.catch_rate == null ? null : `Catch rate ${formatPct(round.catch_rate)}`,
    round.false_block_rate == null ? null : `False-block rate ${formatPct(round.false_block_rate)}`,
  ].filter((line): line is string => !!line);

  return (
    <section className="section round-replay" aria-label="Training replay">
      <p className="label">Replay</p>
      <h2 className="round-replay-title" aria-live="polite">
        Round {round.round}
      </h2>
      {rates.length ? <p className="round-replay-rates">{rates.join(" · ")}</p> : null}
      <ol className="round-replay-lines">
        {visible.map((line) => (
          <li key={`${line.round}-${line.split}-${line.page_id}`}>
            <span>
              {line.store || line.page_id} · {line.page_kind || line.split} · {line.trick}
            </span>
            <span className="round-replay-meta">
              {line.label} → {line.verdict}
              {line.fed_back ? " · fed back" : ""}
              {line.source === "from_miss" ? " · from a miss" : ""}
            </span>
          </li>
        ))}
      </ol>
      {lines.length > MAX_LINES ? (
        <p className="round-replay-more">
          {MAX_LINES} of {lines.length}
        </p>
      ) : null}
    </section>
  );
}
