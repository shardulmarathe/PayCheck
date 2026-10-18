import type { CSSProperties, ReactNode } from "react";

/**
 * Checkpoint signage: every section header reads like a document header, e.g. "INSPECTION 02 · How it works".
 * The visible words are the section's existing kicker; the number is wayfinding only.
 */
export function Sign({ n, id, children, as = "h2" }: { n: string; id?: string; children: ReactNode; as?: "h2" | "h3" | "p" }) {
  const Tag = as;
  return (
    <Tag id={id} className="cp-sign">
      <span className="cp-sign-t" data-n={n}>{children}</span>
    </Tag>
  );
}

/** Luggage-style inspection tag: punched hole, string, verdict word, one plain line. */
export function Tag({ verdict, label, detail, className = "", style }: { verdict: "held" | "cleared"; label?: string; detail?: ReactNode; className?: string; style?: CSSProperties }) {
  return (
    <span className={`cp-tag is-${verdict} ${className}`} style={style}>
      <span className="cp-tag-string" aria-hidden="true" />
      <span className="cp-tag-body">
        <span className="cp-tag-hole" aria-hidden="true" />
        {label ? <span className="cp-tag-label">{label}</span> : null}
        <span className="cp-tag-verdict">{verdict === "held" ? "HELD" : "CLEARED"}</span>
        {detail ? <span className="cp-tag-detail">{detail}</span> : null}
      </span>
    </span>
  );
}
