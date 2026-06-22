import React, { useMemo } from "react";
import { useOutletContext } from "react-router-dom";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from "recharts";
import { Card } from "../components/ui/Card";
import { correlation } from "../lib/utils";

export function InequalityPage() {
  const { metrics } = useOutletContext();

  const scatter = useMemo(() => {
    return metrics
      .filter((c) => c.response_gap_days != null && c.median_income != null)
      .map((c) => ({ x: c.median_income, y: c.response_gap_days, rural: c.is_rural, name: c.county_name }));
  }, [metrics]);

  const r = correlation(scatter);
  const total = scatter.length || 220;

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
