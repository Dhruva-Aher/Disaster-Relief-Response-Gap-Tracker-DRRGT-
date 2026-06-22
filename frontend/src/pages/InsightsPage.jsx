import React from "react";
import { useOutletContext } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { useAnalytics } from "../features/api/hooks";
import { correlation } from "../lib/utils";
import { api } from "../lib/api";

export function InsightsPage() {
  const { metrics } = useOutletContext();
  const { data: insights, isLoading } = useAnalytics("insights");

  const scatter = metrics
    .filter((c) => c.response_gap_days != null && c.median_income != null)
    .map((c) => ({ x: c.median_income, y: c.response_gap_days, rural: c.is_rural }));

  const stats = insights?.stats || {};
  const r = Number.isFinite(stats.pearson_r) ? stats.pearson_r.toFixed(2) : Number.isFinite(correlation(scatter)) ? correlation(scatter).toFixed(2) : "—";
  const ruralCount = metrics.filter((m) => m.is_rural).length;
  const urbanCount = metrics.filter((m) => !m.is_rural).length;
  const avgRural = stats.rural_median_gap ?? null;
  const avgUrban = stats.urban_median_gap ?? null;

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

  const handleExportStates = () => {
    window.location.href = api.export.states("csv");
  };

  return (
    <Card title="Key Insights" subtitle="Auto-generated takeaways from the backend analysis.">
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "16px" }}>
        <button className="btn btn-outline" onClick={handleExportStates}>Export States (CSV)</button>
      </div>
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
        {isLoading && <div className="empty-state">Loading insights...</div>}
        {(insights?.insights || []).map((msg, idx) => (
          <div key={idx} className="ins-note">
            {msg}
          </div>
        ))}
        {!isLoading && !(insights?.insights?.length) ? <div className="empty-state">Run the ETL pipeline to generate more insights.</div> : null}
      </div>
    </Card>
  );
}
