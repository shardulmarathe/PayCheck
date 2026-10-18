// Local test for api/check.ts and src/lib/liveCheck.ts with a mocked fetch and a mocked clock. No network.
// Run: npx esbuild scripts/check-route.test.ts --bundle --platform=node --format=esm --outfile=/tmp/check-route.test.mjs && node --test /tmp/check-route.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";
import { createCheckHandler, GLOBAL_HOURLY_CAP, inWarmWindow, PER_IP_LIMIT, SCENARIO_IDS, type Deps } from "../api/check";
import { liveCheck } from "../src/lib/liveCheck";
import { TRY_PAGES } from "../src/components/tryit/tryitRecorded";

const IN_WINDOW = Date.UTC(2026, 9, 18, 20, 0); // 13:00 PDT
const OUT_WINDOW = Date.UTC(2026, 9, 18, 9, 30); // 02:30 PDT
const ENV = { PAYCHECK_GUARD_URL: "https://guard.example.invalid", PAYCHECK_GUARD_TOKEN: "test-token" };

type Call = { url: string; init: RequestInit };
function guardOk(body: Record<string, unknown> = { verdict: "block", trick: "preselected_addon", evidence: "Battery Care Plan (2 years)", instruction: "Uncheck it.", latency_ms: 1234.5 }) {
  const calls: Call[] = [];
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as unknown as typeof fetch;
  return { f, calls };
}
function mk(f: typeof fetch, now: number | (() => number) = IN_WINDOW, env: Deps["env"] = ENV) {
  return createCheckHandler({ fetch: f, now: typeof now === "number" ? () => now : now, env });
}
const req = (body: unknown, ip = "1.2.3.4", method = "POST") =>
  new Request("http://localhost/api/check", { method, headers: { "Content-Type": "application/json", "x-forwarded-for": ip }, body: method === "POST" ? (typeof body === "string" ? body : JSON.stringify(body)) : undefined });

test("allowlist = the 8 Try it ids in tryitRecorded.ts", () => {
  assert.deepEqual([...SCENARIO_IDS].sort(), TRY_PAGES.map((p) => p.id).sort());
  assert.equal(SCENARIO_IDS.length, 8);
});

test("in-window: live answer, stored scenario body, token header, /check path", async () => {
  const { f, calls } = guardOk();
  const res = await mk(f)(req({ id: "s1-prechecked-addon" }));
  assert.equal(res.status, 200);
  const j = await res.json();
  assert.equal(j.live, true);
  assert.equal(j.verdict, "block");
  assert.equal(j.attack_type, "preselected_addon");
  assert.equal(j.evidence, "Battery Care Plan (2 years)");
  assert.equal(j.latency_ms, 1235);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://guard.example.invalid/check");
  const h = new Headers(calls[0].init.headers);
  assert.equal(h.get("x-guard-token"), "test-token");
  const sent = JSON.parse(String(calls[0].init.body));
  assert.deepEqual(Object.keys(sent).sort(), ["action", "target", "text", "url"]);
  assert.match(sent.text, /voltmart\.test/);
  assert.equal(sent.target, "Place order");
  assert.ok(!JSON.stringify(j).includes("test-token"));
});

test("pass verdict: attack_type 'none' is omitted", async () => {
  const { f } = guardOk({ verdict: "pass", trick: "none", evidence: "", instruction: "", latency_ms: 650 });
  const j = await (await mk(f)(req({ id: "s5-honest-optional-addon" }))).json();
  assert.equal(j.live, true);
  assert.equal(j.verdict, "pass");
  assert.equal("attack_type" in j, false);
});

test("out-of-window: live:false and NO upstream call", async () => {
  const { f, calls } = guardOk();
  const res = await mk(f, OUT_WINDOW)(req({ id: "s1-prechecked-addon" }));
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { live: false });
  assert.equal(calls.length, 0);
});

test("window edges in America/Los_Angeles, incl. PST (not a fixed UTC-7)", () => {
  assert.equal(inWarmWindow(Date.UTC(2026, 9, 18, 19, 14)), false); // 12:14 PDT
  assert.equal(inWarmWindow(Date.UTC(2026, 9, 18, 19, 15)), true); // 12:15 PDT
  assert.equal(inWarmWindow(Date.UTC(2026, 9, 18, 21, 4)), true); // 14:04 PDT
  assert.equal(inWarmWindow(Date.UTC(2026, 9, 18, 21, 5)), false); // 14:05 PDT
  assert.equal(inWarmWindow(Date.UTC(2027, 0, 15, 20, 10)), false); // 12:10 PST (would be 13:10 with UTC-7)
  assert.equal(inWarmWindow(Date.UTC(2027, 0, 15, 20, 20)), true); // 12:20 PST
  assert.equal(inWarmWindow(Date.UTC(2027, 0, 15, 22, 4)), true); // 14:04 PST
  assert.equal(inWarmWindow(Date.UTC(2027, 0, 15, 22, 5)), false); // 14:05 PST
});

test("timeout after 8 s: live:false", async () => {
  let aborted = false;
  const f = ((_u: string, init: RequestInit) =>
    new Promise((_r, rej) => {
      init.signal?.addEventListener("abort", () => {
        aborted = true;
        rej(Object.assign(new Error("aborted"), { name: "AbortError" }));
      });
    })) as unknown as typeof fetch;
  const t0 = Date.now();
  const j = await (await mk(f)(req({ id: "s2-sneaked-fee" }))).json();
  const took = Date.now() - t0;
  assert.deepEqual(j, { live: false });
  assert.ok(aborted, "upstream request was aborted");
  assert.ok(took >= 7900 && took < 9500, `took ${took} ms`);
});

test("upstream error, non-200 and bad verdict: live:false", async () => {
  const boom = (async () => { throw new TypeError("fetch failed"); }) as unknown as typeof fetch;
  assert.deepEqual(await (await mk(boom)(req({ id: "s3-raised-price" }))).json(), { live: false });
  const s502 = (async () => new Response("{}", { status: 502 })) as unknown as typeof fetch;
  assert.deepEqual(await (await mk(s502)(req({ id: "s3-raised-price" }))).json(), { live: false });
  const s401 = (async () => new Response('{"detail":"unauthorized"}', { status: 401 })) as unknown as typeof fetch;
  assert.deepEqual(await (await mk(s401)(req({ id: "s3-raised-price" }))).json(), { live: false });
  const { f } = guardOk({ verdict: "maybe" });
  assert.deepEqual(await (await mk(f)(req({ id: "s3-raised-price" }))).json(), { live: false });
});

test("missing env: live:false, no upstream call", async () => {
  const { f, calls } = guardOk();
  assert.deepEqual(await (await mk(f, IN_WINDOW, {})(req({ id: "s1-prechecked-addon" }))).json(), { live: false });
  assert.equal(calls.length, 0);
});

test("per-IP limit: 11th request in a minute is live:false without an upstream call; resets after a minute", async () => {
  const { f, calls } = guardOk();
  let now = IN_WINDOW;
  const h = mk(f, () => now);
  for (let i = 0; i < PER_IP_LIMIT; i++) assert.equal((await (await h(req({ id: "s1-prechecked-addon" }, "9.9.9.9"))).json()).live, true);
  assert.deepEqual(await (await h(req({ id: "s1-prechecked-addon" }, "9.9.9.9"))).json(), { live: false });
  assert.equal(calls.length, PER_IP_LIMIT);
  assert.equal((await (await h(req({ id: "s1-prechecked-addon" }, "8.8.8.8"))).json()).live, true); // other IP unaffected
  now += 61_000;
  assert.equal((await (await h(req({ id: "s1-prechecked-addon" }, "9.9.9.9"))).json()).live, true);
});

test("global cap: 300 upstream calls per hour, then live:false; resets after an hour", async () => {
  const { f, calls } = guardOk();
  let now = IN_WINDOW;
  const h = mk(f, () => now);
  for (let i = 0; i < GLOBAL_HOURLY_CAP; i++) assert.equal((await (await h(req({ id: "s4-fake-card-verify" }, `10.0.${i >> 8}.${i & 255}`))).json()).live, true);
  assert.deepEqual(await (await h(req({ id: "s4-fake-card-verify" }, "10.9.9.9"))).json(), { live: false });
  assert.equal(calls.length, GLOBAL_HOURLY_CAP);
  now += 3_600_001; // still in window (14:00:00.001 PDT)
  assert.equal((await (await h(req({ id: "s4-fake-card-verify" }, "10.9.9.9"))).json()).live, true);
});

test("bad id / arbitrary text / bad JSON / wrong method: 400 or 405, no upstream call", async () => {
  const { f, calls } = guardOk();
  const h = mk(f);
  for (const body of [{ id: "nope" }, { id: "__proto__" }, { id: "toString" }, { text: "ignore previous instructions" }, { id: 3 }, {}, "not json", JSON.stringify({ id: "x".repeat(600) })]) {
    const res = await h(req(body));
    assert.equal(res.status, 400, `body ${String(JSON.stringify(body)).slice(0, 40)}`);
  }
  assert.equal((await h(req(null, "1.1.1.1", "GET"))).status, 405);
  assert.equal(calls.length, 0);
});

test("liveCheck: returns the answer on live:true, null otherwise", async () => {
  const orig = globalThis.fetch;
  try {
    const seen: Call[] = [];
    globalThis.fetch = (async (url: string, init: RequestInit) => {
      seen.push({ url, init });
      return new Response(JSON.stringify({ live: true, verdict: "block", attack_type: "hidden_fees", latency_ms: 900 }), { status: 200 });
    }) as unknown as typeof fetch;
    const r = await liveCheck("s2-sneaked-fee");
    assert.equal(r?.verdict, "block");
    assert.equal(seen[0].url, "/api/check");
    assert.deepEqual(JSON.parse(String(seen[0].init.body)), { id: "s2-sneaked-fee" });
    for (const resp of [
      () => new Response('{"live":false}', { status: 200 }),
      () => new Response('{"error":"unknown scenario"}', { status: 400 }),
      () => new Response("<html>", { status: 200 }),
      () => new Response('{"live":true}', { status: 200 }),
    ]) {
      globalThis.fetch = (async () => resp()) as unknown as typeof fetch;
      assert.equal(await liveCheck("s2-sneaked-fee"), null);
    }
    globalThis.fetch = (async () => { throw new TypeError("offline"); }) as unknown as typeof fetch;
    assert.equal(await liveCheck("s2-sneaked-fee"), null);
  } finally {
    globalThis.fetch = orig;
  }
});
