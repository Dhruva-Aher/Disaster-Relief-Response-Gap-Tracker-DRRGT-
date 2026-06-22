import React from "react";
import { useParams, Link } from "react-router-dom";
import { useStateReport } from "../features/api/hooks";
import { api } from "../lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/Card";
import { StatCard } from "../components/ui/StatCard";

export default function StateReportPage() {
  const { state } = useParams();
  const { data, isLoading, isError } = useStateReport(state?.toUpperCase());

  if (isLoading) return <div className="p-8">Loading research report...</div>;
  if (isError || !data) return <div className="p-8 text-red-500">Failed to load report.</div>;

  return (
    <div className="max-w-5xl mx-auto space-y-8 print:m-0 print:max-w-full">
      
      {/* Header and Controls */}
      <div className="flex justify-between items-start print:hidden">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">State of {data.state}</h1>
          <p className="text-sm text-slate-500 mt-1">Disaster Relief Equity Report</p>
        </div>
        <div className="space-x-4">
          <a href={api.export.stateReport(data.state, "csv")} className="text-sm bg-slate-100 px-4 py-2 rounded border hover:bg-slate-200">
            Download CSV
          </a>
          <button onClick={() => window.print()} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            Print / PDF
          </button>
        </div>
      </div>

      {/* Print-only Header */}
      <div className="hidden print:block border-b-2 border-slate-900 pb-4 mb-8">
        <h1 className="text-4xl font-bold text-slate-900">State of {data.state}</h1>
        <p className="text-slate-600">Disaster Relief Equity Report</p>
        <p className="text-xs text-slate-500 mt-2">Generated: {new Date().toLocaleDateString()}</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <StatCard label="Avg Response Gap" value={data.avg_response_gap_days ? `${data.avg_response_gap_days.toFixed(1)} days` : "N/A"} />
        <StatCard label="National State Rank" value={data.national_state_rank || "N/A"} sublabel={`out of ${data.total_states_ranked} states`} />
        <StatCard label="Counties Tracked" value={data.county_rankings?.length || 0} />
      </div>

      {/* Historical Trend */}
      <Card>
        <CardHeader>
          <CardTitle>Historical Trend</CardTitle>
        </CardHeader>
        <CardContent>
          {data.historical_trend?.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                  <tr>
                    <th className="px-4 py-2">Year</th>
                    <th className="px-4 py-2">State Avg Gap (Days)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.historical_trend.map(t => (
                    <tr key={t.year} className="border-b">
                      <td className="px-4 py-2">{t.year}</td>
                      <td className="px-4 py-2">{t.avg_gap.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-slate-500">Insufficient historical data.</p>
          )}
        </CardContent>
      </Card>

      {/* County Rankings */}
      <Card>
        <CardHeader>
          <CardTitle>County Rankings</CardTitle>
          <p className="text-sm text-slate-500">Ranked by longest average response gap.</p>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto max-h-[600px]">
            <table className="w-full text-sm text-left relative">
              <thead className="text-xs text-slate-500 uppercase bg-slate-50 sticky top-0 border-b">
                <tr>
                  <th className="px-4 py-3">State Rank</th>
                  <th className="px-4 py-3">County</th>
                  <th className="px-4 py-3">Avg Gap</th>
                  <th className="px-4 py-3 text-right print:hidden">Action</th>
                </tr>
              </thead>
              <tbody>
                {data.county_rankings?.map(c => (
                  <tr key={c.fips} className="border-b hover:bg-slate-50">
                    <td className="px-4 py-2 font-medium text-slate-600">#{c.state_rank}</td>
                    <td className="px-4 py-2">{c.name}</td>
                    <td className="px-4 py-2">{c.avg_response_gap_days ? c.avg_response_gap_days.toFixed(1) : "N/A"} days</td>
                    <td className="px-4 py-2 text-right print:hidden">
                      <Link to={`/report/county/${c.fips}`} className="text-blue-600 hover:underline">View Report &rarr;</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* Credibility / Methodology Footer */}
      <div className="mt-12 pt-8 border-t border-slate-200 text-xs text-slate-600 space-y-4">
        <div>
          <h4 className="font-bold text-slate-800 uppercase tracking-wider mb-1">Methodology</h4>
          <p>{data.methodology}</p>
        </div>
        <div>
          <h4 className="font-bold text-slate-800 uppercase tracking-wider mb-1">Limitations</h4>
          <p>{data.limitations}</p>
        </div>
        <div>
          <h4 className="font-bold text-slate-800 uppercase tracking-wider mb-1">Sources</h4>
          <p>{data.sources}</p>
        </div>
        <div>
          <span className="font-bold text-slate-800">Last Updated:</span> {new Date(data.last_updated).toLocaleString()}
        </div>
      </div>

    </div>
  );
}
