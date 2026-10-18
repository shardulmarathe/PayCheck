/**
 * Client helper for the Try it demo: asks /api/check for a live guard answer on one of the 8 stored scenarios.
 * Returns the live answer only when the server says live:true; on anything else (outside the 12:15–2:05 PM PT
 * warm window, rate limited, timeout, network error, non-200, malformed JSON) it returns null, and the caller
 * shows the recorded result. No keys or guard address live here; the server route holds them.
 */
export interface LiveCheck {
  live: true;
  verdict: "block" | "pass";
  attack_type?: string;
  evidence?: string;
  instruction?: string;
  /** Guard-reported model time for this check. */
  latency_ms: number;
  /** Server-measured round trip to the guard. */
  roundtrip_ms?: number;
}

export async function liveCheck(scenarioId: string, opts: { signal?: AbortSignal; timeoutMs?: number } = {}): Promise<LiveCheck | null> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), opts.timeoutMs ?? 10_000);
  const onAbort = () => ctrl.abort();
  opts.signal?.addEventListener("abort", onAbort, { once: true });
  try {
    const res = await fetch("/api/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: scenarioId }),
      signal: ctrl.signal,
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as Partial<LiveCheck> & { live?: unknown };
    if (data?.live !== true || (data.verdict !== "block" && data.verdict !== "pass") || typeof data.latency_ms !== "number") return null;
    return data as LiveCheck;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
    opts.signal?.removeEventListener("abort", onAbort);
  }
}
