import React from "react";
import { Link } from "react-router-dom";
import { useOutlierReport } from "../features/api/hooks";
import { api } from "../lib/api";
import { Card, CardHeader, CardTitle, CardContent } from "../components/ui/Card";

export default function OutliersPage() {
  const { data, isLoading, isError } = useOutlierReport();

  if (isLoading) return <div className="p-8">Loading research report...</div>;
  if (isError || !data) return <div className="p-8 text-red-500">Failed to load report.</div>;

  const renderTable = (title, items) => (
    <Card className="mb-8 break-inside-avoid">
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {items?.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-slate-500 uppercase bg-slate-50 border-b">
                <tr>
                  <th className="px-4 py-2">County</th>
                  <th className="px-4 py-2">State</th>
                  <th className="px-4 py-2">Value</th>
                  <th className="px-4 py-2 w-1/2">Reasoning</th>
                  <th className="px-4 py-2 text-right print:hidden">Report</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c, i) => (
                  <tr key={`${c.fips}-${i}`} className="border-b hover:bg-slate-50">
                    <td className="px-4 py-2 font-medium">{c.name}</td>
                    <td className="px-4 py-2">{c.state}</td>
                    <td className="px-4 py-2">{c.value ? c.value.toFixed(1) : "N/A"}</td>
                    <td className="px-4 py-2 text-slate-600">{c.reasoning}</td>
                    <td className="px-4 py-2 text-right print:hidden">
                      <Link to={`/report/county/${c.fips}`} className="text-blue-600 hover:underline">View &rarr;</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-slate-500">No counties met the criteria for this category.</p>
        )}
      </CardContent>
    </Card>
  );

  return (
    <div className="max-w-6xl mx-auto space-y-8 print:m-0 print:max-w-full">
      
      {/* Header and Controls */}
      <div className="flex justify-between items-start print:hidden">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">National Outliers Report</h1>
          <p className="text-sm text-slate-500 mt-1">Disaster Relief Equity Report</p>
        </div>
        <div className="space-x-4">
          <a href={api.export.outlierReport("csv")} className="text-sm bg-slate-100 px-4 py-2 rounded border hover:bg-slate-200">
            Download CSV
          </a>
          <button onClick={() => window.print()} className="text-sm bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700">
            Print / PDF
          </button>
        </div>
      </div>

      {/* Print-only Header */}
      <div className="hidden print:block border-b-2 border-slate-900 pb-4 mb-8">
        <h1 className="text-4xl font-bold text-slate-900">National Outliers Report</h1>
        <p className="text-slate-600">Disaster Relief Equity Report</p>
        <p className="text-xs text-slate-500 mt-2">Generated: {new Date().toLocaleDateString()}</p>
      </div>

      {renderTable("Most Underserved Counties", data.most_underserved)}
      {renderTable("Most Improved Counties", data.most_improved)}
      {renderTable("Consistently Underserved Counties", data.consistently_underserved)}

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
