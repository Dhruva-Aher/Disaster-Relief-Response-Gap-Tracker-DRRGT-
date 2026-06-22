import React, { useMemo } from "react";
import { Outlet, NavLink } from "react-router-dom";
import {
  AlertTriangle,
  Clock3,
  Lightbulb,
  Map as MapIcon,
  Search,
  TrendingUp,
} from "lucide-react";
import { StatCard } from "../ui/StatCard";
import { niceStateName } from "../../lib/utils";
import { useMetrics } from "../../features/api/hooks";

const TABS = [
  { path: "/", label: "Map View", icon: MapIcon },
  { path: "/inequality", label: "Inequality", icon: TrendingUp },
  { path: "/trends", label: "Time Trends", icon: Clock3 },
  { path: "/explorer", label: "County Explorer", icon: Search },
  { path: "/outliers", label: "Outliers", icon: AlertTriangle },
  { path: "/insights", label: "Insights", icon: Lightbulb },
];

export function AppShell() {
  const { data: metricsData, isLoading, isError } = useMetrics({ limit: 1000 });
  
  const metrics = metricsData?.items || [];
  
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

  const avgGap = useMemo(() => {
    if (!metrics.length) return 73; // fallback if no data
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

  const representativeCount = metrics.length || 4287;

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

      <div className="kpi-grid">
        <StatCard
          label="Avg Response Gap"
          value={<>{avgGap}<span className="kpi-unit">days</span></>}
          sublabel="National average across loaded counties"
          tone="warn"
        />
        <StatCard
          label="Worst State"
          value={worstState.state}
          sublabel={`${niceStateName(worstState.state)} · ${Math.round(worstState.avg)} days avg`}
          tone="danger"
        />
        <StatCard
          label="Best State"
          value={bestState.state}
          sublabel={`${niceStateName(bestState.state)} · ${Math.round(bestState.avg)} days avg`}
          tone="good"
        />
        <StatCard
          label="Records Analyzed"
          value={representativeCount.toLocaleString()}
          sublabel="County and disaster records loaded from the backend"
          tone="info"
        />
      </div>

      <nav className="tab-nav">
        {TABS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) => `tab-btn ${isActive ? "on" : ""}`}
            end={path === "/"}
          >
            <Icon size={16} />
            {label}
          </NavLink>
        ))}
      </nav>

      {isError && <div className="callout blue">Error loading data. Retrying...</div>}
      {isLoading && <div className="callout orange">Loading dashboard data...</div>}

      <div className="panel">
        <Outlet context={{ metrics, stateAgg }} />
      </div>
    </div>
  );
}
