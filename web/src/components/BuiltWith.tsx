import { SITE } from "../lib/copy";

export function BuiltWith() {
  return (
    <div className="wrap">
      <section className="section built" aria-labelledby="tracks-title">
        <p className="cp-doc-head" aria-hidden="true">
          <span>Hackathon</span>
          <span>Entry form</span>
        </p>
        <h2 id="tracks-title" className="built-title">
          <span className="cp-n">01</span> {SITE.tracksTitle}
        </h2>
        <ul className="built-list">
          {SITE.tracks.map((track) => (
            <li key={track}>{track}</li>
          ))}
        </ul>
        <p className="body built-line">
          <span className="built-k">
            <span className="cp-n">02</span> {SITE.builtTitle}:
          </span> {SITE.builtWith.join(" · ")}
        </p>
      </section>
    </div>
  );
}
