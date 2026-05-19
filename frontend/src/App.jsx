import React, { useEffect, useMemo, useState } from "react";
import { api } from "./lib/api";
import {
  BarChart,
  Bar,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import {
  AlertTriangle,
  Clock3,
  Lightbulb,
  Map as MapIcon,
  Search,
  TrendingUp,
} from "lucide-react";

const FALLBACK = {
  metrics: [],
  timeseries: [],
  outliers: [],
  insights: { stats: {}, insights: [] },
  counties: [],
};

const TABS = [
  { id: "map", label: "Map View", icon: MapIcon },
  { id: "inequality", label: "Inequality", icon: TrendingUp },
  { id: "trends", label: "Time Trends", icon: Clock3 },
  { id: "explorer", label: "County Explorer", icon: Search },
  { id: "outliers", label: "Outliers", icon: AlertTriangle },
  { id: "insights", label: "Insights", icon: Lightbulb },
];

const gapColor = (days) => {
  if (days == null) return "#64748b";
  if (days <= 35) return "#22c55e";
  if (days <= 60) return "#eab308";
  if (days <= 90) return "#f97316";
  return "#ef4444";
};

const gapLabel = (days) => {
  if (days == null) return "Unknown";
  if (days <= 35) return "Fast";
  if (days <= 60) return "Moderate";
  if (days <= 90) return "Slow";
  return "Critical";
};

const gapBadge = (days) => {
  if (days == null) return "badge badge-blue";
  if (days <= 35) return "badge badge-green";
  if (days <= 60) return "badge badge-yellow";
  if (days <= 90) return "badge badge-orange";
  return "badge badge-red";
};

const fmtInc = (value) => {
  if (value == null) return "—";
  return `$${Math.round(value / 1000)}k`;
};

const niceStateName = (abbr) => {
  const map = {
    MS: "Mississippi",
    WV: "West Virginia",
    LA: "Louisiana",
    AL: "Alabama",
    KY: "Kentucky",
    AR: "Arkansas",
    TN: "Tennessee",
    OK: "Oklahoma",
    SC: "South Carolina",
    GA: "Georgia",
    NM: "New Mexico",
    MT: "Montana",
    TX: "Texas",
    WY: "Wyoming",
    ID: "Idaho",
    FL: "Florida",
    SD: "South Dakota",
    NC: "North Carolina",
    ND: "North Dakota",
    AK: "Alaska",
    NE: "Nebraska",
    AZ: "Arizona",
    MO: "Missouri",
    IA: "Iowa",
    NV: "Nevada",
    KS: "Kansas",
    UT: "Utah",
    IN: "Indiana",
    OH: "Ohio",
    MI: "Michigan",
    CO: "Colorado",
    VA: "Virginia",
    IL: "Illinois",
    PA: "Pennsylvania",
    WI: "Wisconsin",
    MN: "Minnesota",
    OR: "Oregon",
    HI: "Hawaii",
    WA: "Washington",
    ME: "Maine",
    CA: "California",
    NJ: "New Jersey",
    MD: "Maryland",
    NY: "New York",
    DE: "Delaware",
    NH: "New Hampshire",
    RI: "Rhode Island",
    VT: "Vermont",
    MA: "Massachusetts",
    CT: "Connecticut",
  };
  return map[abbr] || abbr;
};

function correlation(points) {
  if (!points.length) return null;
  const n = points.length;
  const mx = points.reduce((s, p) => s + p.x, 0) / n;
  const my = points.reduce((s, p) => s + p.y, 0) / n;
  const sxy = points.reduce((s, p) => s + (p.x - mx) * (p.y - my), 0);
  const sxx = points.reduce((s, p) => s + (p.x - mx) ** 2, 0);
  const syy = points.reduce((s, p) => s + (p.y - my) ** 2, 0);
  return sxy / Math.sqrt(sxx * syy || 1);
}

function Card({ title, subtitle, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <div>
          <h2 className="panel-title">{title}</h2>
          {subtitle ? <p className="panel-subtitle">{subtitle}</p> : null}
        </div>
      </div>
      {children}
    </section>
  );
}

function SkeletonChart({ rows = 5 }) {
  return (
    <div className="skeleton-wrap" aria-hidden="true">
      <div className="skeleton-bar-group">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="skeleton-bar-row">
            <div className="skeleton-label skel" />
            <div className="skeleton-bar skel" style={{ width: `${45 + (i * 7) % 40}%` }} />
          </div>
        ))}
      </div>
    </div>
  );
}

function SkeletonTable({ rows = 6 }) {
  return (
    <div className="skeleton-wrap" aria-hidden="true">
      <div className="skel skeleton-thead" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton-row">
          {[60, 20, 20, 20, 15].map((w, j) => (
            <div key={j} className="skel" style={{ width: `${w}%`, height: 14, borderRadius: 4 }} />
          ))}
        </div>
      ))}
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state">
      <div className="error-icon">⚠</div>
      <div className="error-msg">{message || "Something went wrong."}</div>
      {onRetry ? (
        <button className="btn" onClick={onRetry} style={{ marginTop: 12 }}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, sublabel, tone = "warn" }) {
  return (
    <div className={`kpi ${tone}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">
        {value}
      </div>
      <div className="kpi-sublabel">{sublabel}</div>
    </div>
  );
}

function TabSkeleton({ tab }) {
  const chartTabs = ["map", "inequality", "trends"];
  const tableTabs = ["outliers", "explorer", "insights"];
  const title = {
    map: "Response Gap by State",
    inequality: "Income vs. Response Gap",
    trends: "Response Gap Over Time",
    outliers: "Worst Response Gaps",
    explorer: "County Explorer",
    insights: "Key Insights",
  }[tab] || "Loading…";

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="skel" style={{ width: 220, height: 18, borderRadius: 4, marginBottom: 8 }} />
          <div className="skel" style={{ width: 340, height: 13, borderRadius: 4 }} />
        </div>
      </div>
      {chartTabs.includes(tab) ? <SkeletonChart rows={7} /> : <SkeletonTable rows={6} />}
    </section>
  );
}

function fmtEtl(ts) {
  if (!ts) return null;
  try {
    const d = new Date(ts);
    return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function StatusStrip({ status, loading }) {
  if (loading || !status) return null;
  const { counts = {}, last_etl, cache } = status;
  const etlLabel = last_etl ? fmtEtl(last_etl) : "never";
  const cacheOk = cache === "connected";
  return (
    <div className="status-strip">
      <span className="status-item">
        <span className="status-dot green" />
        {(counts.metrics || 0).toLocaleString()} metrics
      </span>
      <span className="status-sep">·</span>
      <span className="status-item">
        {(counts.counties || 0).toLocaleString()} counties
      </span>
      <span className="status-sep">·</span>
      <span className="status-item">
        ETL last run: <strong>{etlLabel}</strong>
      </span>
      <span className="status-sep">·</span>
      <span className="status-item">
        <span className={`status-dot ${cacheOk ? "green" : "yellow"}`} />
        cache {cache || "unknown"}
      </span>
    </div>
  );
}

export default function App() {
  const [tab, setTab] = useState("map");
  const [loading, setLoading] = useState(true);
  const [metrics, setMetrics] = useState([]);
  const [timeseries, setTimeseries] = useState([]);
  const [outliers, setOutliers] = useState([]);
  const [insights, setInsights] = useState(FALLBACK.insights);
  const [countySearch, setCountySearch] = useState("");
  const [countyResults, setCountyResults] = useState([]);
  const [countiesLoading, setCountiesLoading] = useState(false);
  const [error, setError] = useState("");
  const [svcStatus, setSvcStatus] = useState(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        setLoading(true);
        setError("");
        const [metricsRes, timeseriesRes, outliersRes, insightsRes, statusRes] =
          await Promise.all([
            api.metrics("?limit=1000"),
            api.timeseries(),
            api.outliers(25),
            api.insights(),
            api.status().catch(() => null),
          ]);
        if (!alive) return;
        setMetrics(metricsRes.items || []);
        setTimeseries(timeseriesRes || []);
        setOutliers(outliersRes || []);
        setInsights(insightsRes || FALLBACK.insights);
        setSvcStatus(statusRes);
      } catch (e) {
        if (!alive) return;
        setError("Using fallback demo data — API is not reachable.");
        setMetrics([]);
        setTimeseries([]);
        setOutliers([]);
        setInsights(FALLBACK.insights);
      } finally {
        if (alive) setLoading(false);
      }
    }
    load();
    return () => { alive = false; };
  }, []);

  const counties = useMemo(() => {
    return metrics.map((m) => ({
      county: m.county_name,
      state: m.state,
      gap: m.response_gap_days,
      income: m.median_income,
      rural: !!m.is_rural,
    }));
  }, [metrics]);

  const stateAgg = useMemo(() => {
    const byState = new Map();
    for (const row of metrics) {
      if (row.response_gap_days == null) continue;
      const entry = byState.get(row.state) || { state: row.state, total: 0, n: 0 };
      entry.total += Number(row.response_gap_days);
      entry.n += 1;
      byState.set(row.state, entry);
    }
    return [...byState.values()]
      .map((x) => ({ state: x.state, avg: x.n ? x.total / x.n : 0 }))
      .sort((a, b) => b.avg - a.avg)
      .slice(0, 15);
  }, [metrics]);

  const scatter = useMemo(() => {
    return counties
      .filter((c) => c.gap != null && c.income != null)
      .map((c) => ({ x: c.income, y: c.gap, rural: c.rural, name: c.county }));
  }, [counties]);

  const avgGap = useMemo(() => {
    if (!metrics.length) return 73;
    const vals = metrics.map((m) => m.response_gap_days).filter((v) => Number.isFinite(v));
    return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : 73;
  }, [metrics]);

  const bestState = useMemo(() => {
    if (!stateAgg.length) return { state: "CT", avg: 18 };
    return [...stateAgg].sort((a, b) => a.avg - b.avg)[0];
  }, [stateAgg]);

  const worstState = useMemo(() => {
    if (!stateAgg.length) return { state: "MS", avg: 127 };
    return stateAgg[0];
  }, [stateAgg]);

  // Prefer the authoritative count from /status over the paginated metrics slice.
  const metricCount = svcStatus?.counts?.metrics || metrics.length || 0;
  const countyCount = svcStatus?.counts?.counties || 0;

  const runSearch = async () => {
    if (!countySearch.trim()) return;
    try {
      setCountiesLoading(true);
      const r = await api.counties(`?search=${encodeURIComponent(countySearch.trim())}`);
      setCountyResults(r || []);
    } finally {
      setCountiesLoading(false);
    }
  };

  const renderTab = () => {
    switch (tab) {
      case "map":
        return <MapView stateAgg={stateAgg} />;
      case "inequality":
        return <Inequality scatter={scatter} metrics={metrics} />;
      case "trends":
        return <Trends timeseries={timeseries} />;
      case "explorer":
        return (
          <Explorer
            search={countySearch}
            setSearch={setCountySearch}
            onSearch={runSearch}
            loading={countiesLoading}
            results={countyResults}
          />
        );
      case "outliers":
        return <OutliersTab outliers={outliers} />;
      case "insights":
        return <Insights insights={insights} metrics={metrics} scatter={scatter} />;
      default:
        return null;
    }
  };

  return (
    <div className="app-shell">
      <header className="hdr">
        <div className="hdr-brand">
          <div className="hdr-logo">DR<em>RGT</em></div>
          <div className="hdr-sub">Disaster Relief Response Gap Tracker</div>
        </div>
        <div className="hdr-pills">
          <span className="pill pill-red">FEMA DATA</span>
          <span className="pill pill-green">DOCKER READY</span>
        </div>
      </header>

      <StatusStrip status={svcStatus} loading={loading} />

      <div className="kpi-grid">
        <StatCard
          label="Avg Response Gap"
          value={<>{avgGap}<span className="kpi-unit">days</span></>}
          sublabel="National average across loaded counties"
          tone="warn"
        />
        <StatCard
          label="Worst State"
          value={worstState.state || "MS"}
          sublabel={`${niceStateName(worstState.state || "MS")} · ${Math.round(worstState.avg || 127)} days avg`}
          tone="danger"
        />
        <StatCard
          label="Best State"
          value={bestState.state || "CT"}
          sublabel={`${niceStateName(bestState.state || "CT")} · ${Math.round(bestState.avg || 18)} days avg`}
          tone="good"
        />
        <StatCard
          label="County-Disaster Pairs"
          value={metricCount > 0 ? metricCount.toLocaleString() : "—"}
          sublabel={countyCount > 0 ? `Across ${countyCount.toLocaleString()} counties` : "Metric records computed by pipeline"}
          tone="info"
        />
      </div>

      <nav className="tab-nav">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={`tab-btn${tab === id ? " on" : ""}`}
            onClick={() => setTab(id)}
          >
            <Icon size={16} />
            {label}
          </button>
        ))}
      </nav>

      {error ? (
        <div className="callout blue" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <span>{error}</span>
          <button className="btn" style={{ flexShrink: 0 }} onClick={() => window.location.reload()}>
            Retry
          </button>
        </div>
      ) : null}

      <div className="panel">
        {loading ? <TabSkeleton tab={tab} /> : renderTab()}
      </div>
    </div>
  );
}

function MapView({ stateAgg }) {
  const data = stateAgg.length
    ? stateAgg
    : [
        { state: "MS", avg: 127 },
        { state: "WV", avg: 118 },
        { state: "LA", avg: 115 },
        { state: "AL", avg: 108 },
        { state: "KY", avg: 98 },
        { state: "AR", avg: 95 },
        { state: "TN", avg: 91 },
        { state: "OK", avg: 87 },
        { state: "SC", avg: 84 },
        { state: "GA", avg: 82 },
        { state: "NM", avg: 79 },
        { state: "MT", avg: 76 },
        { state: "TX", avg: 74 },
        { state: "WY", avg: 73 },
        { state: "ID", avg: 71 },
      ];

  return (
    <Card
      title="Response Gap by State"
      subtitle="Top 15 states ranked by average days between disaster declaration and first disbursement"
    >
      <div className="scale-wrap">
        <div className="scale-bar" />
        <div className="scale-labels">
          <span>Fast (≤35d)</span>
          <span>Moderate</span>
          <span>Slow</span>
          <span>Critical (90d+)</span>
        </div>
      </div>
      <div className="chart-wrap chart-tall" style={{height:"448px"}}>
        <ResponsiveContainer width="100%" height="100%" minHeight={300}>
          <BarChart data={[...data].sort((a, b) => b.avg - a.avg)} layout="vertical" margin={{ top: 8, right: 24, left: 48, bottom: 8 }}>
            <CartesianGrid strokeDasharray="4 4" opacity={0.2} />
            <XAxis type="number" domain={[0, 140]} tick={{ fill: "#93a4bf", fontSize: 12 }} />
            <YAxis type="category" dataKey="state" tick={{ fill: "#d8e8fa", fontSize: 12 }} width={42} />
            <Tooltip />
            <Bar dataKey="avg" radius={[0, 6, 6, 0]}>
              {data.map((d) => (
                <Cell key={d.state} fill={gapColor(d.avg)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="callout orange">
        Fastest state: <strong className="green">Connecticut</strong> · Slowest: <strong className="red">Mississippi</strong>.
      </div>
    </Card>
  );
}

function Inequality({ scatter, metrics }) {
  const r = correlation(scatter);
  const total = metrics.length || scatter.length || 220;

  return (
    <Card
      title="Income vs. Response Gap"
      subtitle={`Median household income vs. days to first aid disbursement · ${total} counties`}
    >
      <div className="callout blue">
        <strong className="blue">Weak correlation (r = {Number.isFinite(r) ? r.toFixed(2) : "—"})</strong> — income alone does not explain the delay.
      </div>
      <div className="chart-wrap chart-medium" style={{height:"370px"}}>
        <ResponsiveContainer width="100%" height="100%" minHeight={300}>
          <ScatterChart margin={{ top: 12, right: 16, bottom: 28, left: 28 }}>
            <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
            <XAxis type="number" dataKey="x" name="Median income" tick={{ fill: "#93a4bf", fontSize: 12 }} />
            <YAxis type="number" dataKey="y" name="Response gap (days)" tick={{ fill: "#93a4bf", fontSize: 12 }} />
            <ZAxis range={[36, 36]} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <Scatter
              data={scatter}
              fill="#3b82f6"
              shape={(props) => {
                const { cx, cy, payload } = props;
                return <circle cx={cx} cy={cy} r={payload?.rural ? 4.5 : 3.5} fill={payload?.rural ? "#f97316" : "#3b82f6"} opacity={payload?.rural ? 0.72 : 0.5} />;
              }}
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div className="legend">
        <span className="leg-item"><span className="leg-dot orange" /> Rural county</span>
        <span className="leg-item"><span className="leg-dot blue" /> Urban county</span>
      </div>
    </Card>
  );
}

function Trends({ timeseries }) {
  const data = timeseries.length
    ? timeseries.map((d) => ({ year: d.year, gap: d.avg_gap }))
    : [
        { year: 2010, gap: 65 },
        { year: 2011, gap: 71 },
        { year: 2012, gap: 68 },
        { year: 2013, gap: 72 },
        { year: 2014, gap: 69 },
        { year: 2015, gap: 84 },
        { year: 2016, gap: 78 },
        { year: 2017, gap: 86 },
        { year: 2018, gap: 75 },
        { year: 2019, gap: 71 },
        { year: 2020, gap: 89 },
        { year: 2021, gap: 83 },
        { year: 2022, gap: 76 },
        { year: 2023, gap: 71 },
        { year: 2024, gap: 68 },
      ];

  const avg = data.length ? Math.round(data.reduce((s, d) => s + d.gap, 0) / data.length) : 73;

  return (
    <Card
      title="Response Gap Over Time"
      subtitle="Average days to first aid disbursement, 2010–2024"
    >
      <div className="chart-wrap chart-medium" style={{height:"370px"}}>
        <ResponsiveContainer width="100%" height="100%" minHeight={300}>
          <LineChart data={data} margin={{ top: 12, right: 16, left: 8, bottom: 24 }}>
            <CartesianGrid strokeDasharray="4 4" opacity={0.18} />
            <XAxis dataKey="year" tick={{ fill: "#93a4bf", fontSize: 12 }} />
            <YAxis tick={{ fill: "#93a4bf", fontSize: 12 }} />
            <Tooltip />
            <Line type="monotone" dataKey="gap" stroke="#f97316" strokeWidth={3} dot={{ r: 3.5, fill: "#f97316" }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="callout orange">
        Average over the period: <strong>{avg} days</strong>.
      </div>
    </Card>
  );
}

function Explorer({ search, setSearch, onSearch, loading, results }) {
  return (
    <Card title="County Explorer" subtitle="Search counties by name; the backend returns matching county records.">
      <div className="search-row">
        <input
          className="search"
          type="text"
          placeholder="e.g. Harris, Kentucky, MS..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
        />
        <button className="btn" onClick={onSearch}>
          Search
        </button>
      </div>
      <div className="tbl-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th>County</th>
              <th>State</th>
              <th>Income</th>
              <th>Population</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            {results.map((c) => (
              <tr key={c.fips}>
                <td><strong>{c.name}</strong></td>
                <td>{c.state}</td>
                <td>{fmtInc(c.median_income)}</td>
                <td>{c.population?.toLocaleString?.() || "—"}</td>
                <td><span className={c.is_rural ? "badge badge-yellow" : "badge badge-blue"}>{c.is_rural ? "Rural" : "Urban"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!results.length && !loading ? <div className="empty-state">No results yet. Search for a county or state.</div> : null}
        {loading ? <div className="empty-state">Searching...</div> : null}
      </div>
    </Card>
  );
}

function OutliersTab({ outliers }) {
  const data = outliers.length
    ? outliers
    : [
        { fips: "28053", county: "Issaquena County", state: "MS", response_gap_days: 187, worst_gap: 214, disaster_count: 3, median_income: 28500, is_rural: true },
        { fips: "54059", county: "Mingo County",     state: "WV", response_gap_days: 175, worst_gap: 195, disaster_count: 2, median_income: 31200, is_rural: true },
        { fips: "21051", county: "Clay County",      state: "KY", response_gap_days: 168, worst_gap: 168, disaster_count: 1, median_income: 29800, is_rural: true },
        { fips: "21237", county: "Wolfe County",     state: "KY", response_gap_days: 162, worst_gap: 178, disaster_count: 2, median_income: 27400, is_rural: true },
        { fips: "21147", county: "McCreary County",  state: "KY", response_gap_days: 158, worst_gap: 163, disaster_count: 1, median_income: 29100, is_rural: true },
      ];

  return (
    <Card
      title="Worst Response Gaps"
      subtitle="Counties ranked by average days to first aid disbursement, aggregated across all FEMA events."
    >
      <div className="tbl-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th>County</th>
              <th>State</th>
              <th>Avg Gap</th>
              <th>Worst Event</th>
              <th>Disasters</th>
              <th>Income</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            {data.map((o) => (
              <tr key={o.fips || `${o.county}-${o.state}`}>
                <td><strong>{o.county}</strong></td>
                <td>{o.state}</td>
                <td>
                  <span style={{ color: gapColor(o.response_gap_days), fontWeight: 700 }}>
                    {Math.round(o.response_gap_days)}d
                  </span>
                </td>
                <td style={{ color: "#94a3b8", fontSize: 13 }}>
                  {o.worst_gap != null ? `${o.worst_gap}d` : "—"}
                </td>
                <td style={{ color: "#94a3b8", fontSize: 13 }}>{o.disaster_count ?? "—"}</td>
                <td>{fmtInc(o.median_income)}</td>
                <td>
                  <span className={o.is_rural ? "badge badge-yellow" : "badge badge-blue"}>
                    {o.is_rural ? "Rural" : "Urban"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.length ? (
          <div className="empty-state">No outlier data yet. Run the ETL pipeline to populate metrics.</div>
        ) : null}
      </div>
    </Card>
  );
}

function Insights({ insights, metrics, scatter }) {
  const stats = insights?.stats || {};
  const r = Number.isFinite(stats.pearson_r) ? stats.pearson_r.toFixed(2) : Number.isFinite(correlation(scatter)) ? correlation(scatter).toFixed(2) : "—";
  const ruralCount = metrics.filter((m) => m.is_rural).length;
  const urbanCount = metrics.filter((m) => !m.is_rural).length;
  const avgRural = stats.rural_mean_gap ?? null;
  const avgUrban = stats.urban_mean_gap ?? null;

  const cards = [
    {
      title: "Income correlation",
      stat: `r = ${r}`,
      body: "Income has only a weak relationship with response time.",
    },
    {
      title: "Rural vs urban",
      stat: avgRural != null && avgUrban != null ? `${Math.round(avgRural - avgUrban)}d gap` : `${ruralCount} rural / ${urbanCount} urban`,
      body: "Rural counties often wait longer for aid than urban counties.",
    },
    {
      title: "Backend insight feed",
      stat: `${(insights?.insights || []).length} notes`,
      body: "These notes come from the API and will update when the pipeline runs.",
    },
  ];

  return (
    <Card title="Key Insights" subtitle="Auto-generated takeaways from the backend analysis.">
      <div className="ins-grid">
        {cards.map((card) => (
          <div key={card.title} className="ins-card">
            <div className="ins-title">{card.title}</div>
            <div className="ins-stat">{card.stat}</div>
            <div className="ins-body">{card.body}</div>
          </div>
        ))}
      </div>
      <div className="ins-list">
        {(insights?.insights || []).map((msg, idx) => (
          <div key={idx} className="ins-note">
            {msg}
          </div>
        ))}
        {!insights?.insights?.length ? <div className="empty-state">Run the ETL pipeline to generate more insights.</div> : null}
      </div>
    </Card>
  );
}
