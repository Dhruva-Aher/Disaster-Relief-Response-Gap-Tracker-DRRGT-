import React from "react";
import { useParams } from "react-router-dom";
import { useCountyReport } from "../features/api/hooks";
import { api } from "../lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/Card";
import { StatCard } from "../components/ui/StatCard";

export default function CountyReportPage() {
  const { fips } = useParams();
  const { data, isLoading, isError } = useCountyReport(fips);

  if (isLoading) return <div className="p-8">Loading research report...</div>;
  if (isError || !data) return <div className="p-8 text-red-500">Failed to load report.</div>;

  return (
    <div className="max-w-5xl mx-auto space-y-8 print:m-0 print:max-w-full">
      
      {/* Header and Controls */}
      <div className="flex justify-between items-start print:hidden">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">{data.name}, {data.state}</h1>
          <p className="text-sm text-slate-500 mt-1">Disaster Relief Equity Report</p>
        </div>
        <div className="space-x-4">
          <a href={api.export.countyReport(fips, "csv")} className="text-sm bg-slate-100 px-4 py-2 rounded border hover:bg-slate-200">
            Download CSV
          </a>
          <button onClick={() => window.print()} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            Print / PDF
          </button>
        </div>
      </div>

      {/* Print-only Header */}
      <div className="hidden print:block border-b-2 border-slate-900 pb-4 mb-8">
        <h1 className="text-4xl font-bold text-slate-900">{data.name}, {data.state}</h1>
        <p className="text-slate-600">Disaster Relief Equity Report</p>
        <p className="text-xs text-slate-500 mt-2">Generated: {new Date().toLocaleDateString()}</p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Avg Response Gap" value={data.avg_response_gap_days ? `${data.avg_response_gap_days.toFixed(1)} days` : "N/A"} />
        <StatCard label="National Percentile" value={data.national_percentile ? `${data.national_percentile.toFixed(1)}%` : "N/A"} sublabel="Higher means longer wait" />
        <StatCard label="National Rank" value={data.national_rank || "N/A"} sublabel={`out of ${data.total_counties_ranked} counties`} />
        <StatCard label="Median Income" value={data.median_income ? `$${data.median_income.toLocaleString()}` : "N/A"} />
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
                    <th className="px-4 py-2">Avg Gap (Days)</th>
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

      {/* Comparable Counties */}
      <Card>
        <CardHeader>
          <CardTitle>Comparable Counties</CardTitle>
          <p className="text-sm text-slate-500">Counties with similar population and median income profiles.</p>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                <tr>
                  <th className="px-4 py-2">County</th>
                  <th className="px-4 py-2">State</th>
                  <th className="px-4 py-2">Population</th>
                  <th className="px-4 py-2">Income</th>
                  <th className="px-4 py-2">Avg Gap</th>
                </tr>
              </thead>
              <tbody>
                {data.comparable_counties?.map(c => (
                  <tr key={c.fips} className="border-b">
                    <td className="px-4 py-2 font-medium">{c.name}</td>
                    <td className="px-4 py-2">{c.state}</td>
                    <td className="px-4 py-2">{c.population?.toLocaleString() || "N/A"}</td>
                    <td className="px-4 py-2">${c.median_income?.toLocaleString() || "N/A"}</td>
                    <td className="px-4 py-2">{c.avg_response_gap_days ? c.avg_response_gap_days.toFixed(1) : "N/A"} days</td>
                  </tr>
                ))}
                {(!data.comparable_counties || data.comparable_counties.length === 0) && (
                  <tr><td colSpan="5" className="px-4 py-4 text-center text-slate-500">No comparable data available.</td></tr>
                )}
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
