import { HiddenTrick } from "../components/HiddenTrick";
import type { Dataset } from "../lib/types";

export function Future({ data }: { data: Dataset }) {
  const future = data.future;
  return (
    <div className="wrap">
      <section className="section">
        <p className="label">{future.kicker}</p>
        <h1 className="h1">
          {future.title_lines[0]}
          <br />
          {future.title_lines[1]}
        </h1>
        <p className="body-l" style={{ marginTop: 20 }}>
          {future.body}
        </p>
      </section>
      <section className="section future-list">
        {future.items.map((item) => (
          <article key={item.n} className="future-row">
            <p className="micro">{item.n}</p>
            <div>
              <h2>{item.title}</h2>
              <p className="body">{item.body}</p>
            </div>
            <p className="micro future-status">{item.status}</p>
          </article>
        ))}
        <HiddenTrick id="future-sub" kind="solid" label="Blocked · subscription trap">
          <span className="trick-box" />
          Subscribe & save 10% · renews at $12.99/mo
        </HiddenTrick>
      </section>
    </div>
  );
}
