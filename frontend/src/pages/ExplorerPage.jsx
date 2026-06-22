import React, { useState } from "react";
import { Card } from "../components/ui/Card";
import { fmtInc } from "../lib/utils";
import { useCounties } from "../features/api/hooks";
import { api } from "../lib/api";

export function ExplorerPage() {
  const [search, setSearch] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  
  const { data: results, isLoading } = useCounties({ search: activeSearch });

  const onSearch = () => {
    setActiveSearch(search.trim());
  };

  const handleExport = () => {
    window.location.href = api.export.counties("csv");
  };

  return (
    <Card title="County Explorer" subtitle="Search counties by name; the backend returns matching county records.">
      <div className="search-row" style={{ display: "flex", gap: "8px", marginBottom: "16px" }}>
        <input
          className="search"
          type="text"
          placeholder="e.g. Harris, Kentucky, MS..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
          style={{ flex: 1 }}
        />
        <button className="btn" onClick={onSearch}>Search</button>
        <button className="btn btn-outline" onClick={handleExport}>Export All (CSV)</button>
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
            {(results || []).map((c) => (
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
        {!(results || []).length && !isLoading ? <div className="empty-state">No results found.</div> : null}
        {isLoading ? <div className="empty-state">Searching...</div> : null}
      </div>
    </Card>
  );
}
