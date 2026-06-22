import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { AppShell } from "./components/layout/AppShell";
import { MapPage } from "./pages/MapPage";
import { InequalityPage } from "./pages/InequalityPage";
import { TrendsPage } from "./pages/TrendsPage";
import { ExplorerPage } from "./pages/ExplorerPage";
import OutliersPage from "./pages/OutliersPage";
import { InsightsPage } from "./pages/InsightsPage";
import CountyReportPage from "./pages/CountyReportPage";
import StateReportPage from "./pages/StateReportPage";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<MapPage />} />
          <Route path="inequality" element={<InequalityPage />} />
          <Route path="trends" element={<TrendsPage />} />
          <Route path="explorer" element={<ExplorerPage />} />
          <Route path="outliers" element={<OutliersPage />} />
          <Route path="insights" element={<InsightsPage />} />
          <Route path="report/county/:fips" element={<CountyReportPage />} />
          <Route path="report/state/:state" element={<StateReportPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
