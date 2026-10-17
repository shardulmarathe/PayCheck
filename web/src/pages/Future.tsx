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
      <div className="section">
        {future.groups.map((group) => (
          <div key={group.label} className="future-group">
            <p className="label future-label">{group.label}</p>
            <div className="future-items">
              {group.items.map((item) => (
                <article key={item.title} className="future-item">
                  <h2 className="title">{item.title}</h2>
                  <p className="body">{item.body}</p>
                </article>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
