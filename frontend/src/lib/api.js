const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
async function j(path) {
  const r = await fetch(`${BASE}${path}`);
  if (!r.ok) throw new Error(`${path} ${r.status}`);
  return r.json();
}
export const api = {
  metrics: (p = "") => j(`/metrics${p}`),
  counties: (q = "") => j(`/counties${q}`),
  correlations: () => j(`/correlations`),
  timeseries: () => j(`/timeseries`),
  outliers: (n = 25) => j(`/outliers?top=${n}`),
  insights: () => j(`/insights`),
};
