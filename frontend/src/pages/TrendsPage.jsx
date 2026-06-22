import React from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "../components/ui/Card";
import { useAnalytics } from "../features/api/hooks";

export function TrendsPage() {
  const { data: timeseriesData, isLoading } = useAnalytics("timeseries");

  const data = timeseriesData && timeseriesData.length
    ? timeseriesData.map((d) => ({ year: d.year, gap: d.avg_gap }))
    : [];

  const avg = data.length ? Math.round(data.reduce((s, d) => s + d.gap, 0) / data.length) : 73;

  return (
    <Card
      title="Response Gap Over Time"
      subtitle="Average days to first aid disbursement, 2010–2024"
    >
      {isLoading ? (
        <div className="empty-state">Loading trends...</div>
      ) : (
        <>
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
        </>
      )}
    </Card>
  );
}
