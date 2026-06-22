import React from "react";
import { useOutletContext } from "react-router-dom";
import { BarChart, Bar, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Card } from "../components/ui/Card";
import { gapColor } from "../lib/utils";

export function MapPage() {
  const { stateAgg } = useOutletContext();
  
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
    </Card>
  );
}
