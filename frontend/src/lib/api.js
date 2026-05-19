const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

async function j(path) {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}

// Returns { data, latencyMs } so callers can surface backend latency.
export async function timed(path) {
  const t0 = performance.now();
  const r = await fetch(`${BASE}${path}`);
  const latencyMs = Math.round(performance.now() - t0);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  const data = await r.json();
  return { data, latencyMs };
}

export const api = {
  metrics:      (p = "") => j(`/metrics${p}`),
  counties:     (q = "")  => j(`/counties${q}`),
  correlations: ()         => j(`/correlations`),
  timeseries:   ()         => j(`/timeseries`),
  outliers:     (n = 25)  => j(`/outliers?top=${n}`),
  insights:     ()         => j(`/insights`),
  status:       ()         => j(`/status`),
};
