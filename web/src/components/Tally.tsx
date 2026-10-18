import { formatTally } from "../lib/format";
import type { TallyItem } from "../lib/types";
import { ExampleMark } from "./Chrome";

export function Tally({
  kicker,
  items,
  example,
  compact = false,
}: {
  kicker: string;
  items: TallyItem[];
  example: boolean;
  compact?: boolean;
}) {
  return (
    <section className="section" aria-labelledby={compact ? "tally-compact" : "tally"}>
      <div className="kicker-row">
        <p className="label" id={compact ? "tally-compact" : "tally"}>
          {kicker}
        </p>
        <ExampleMark show={example} />
      </div>
      <div className={compact ? "tally compact" : "tally"}>
        {items.map((item) => (
          <article key={item.id}>
            <p className="body">{item.label}</p>
            <div className="tally-figure">
              <p className="num-xl">{formatTally(item.with_guard, item.format)}</p>
              <p className={item.from_tone === "loss" ? "num loss" : "num muted"}>
                from {formatTally(item.without_guard, item.format)}
              </p>
            </div>
            <p className="micro tally-note">{item.note}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
