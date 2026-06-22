import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

export function useMetrics(params = {}) {
  return useQuery({
    queryKey: ["metrics", params],
    queryFn: () => api.metrics(params),
  });
}

export const useTrends = () => {
  return useQuery({
    queryKey: ['analytics', 'trends'],
    queryFn: api.analytics.trends,
  });
};

export const useModel = () => {
  return useQuery({
    queryKey: ['analytics', 'model'],
    queryFn: api.analytics.model,
  });
};

// REPORT HOOKS
export const useCountyReport = (fips) => {
  return useQuery({
    queryKey: ['report', 'county', fips],
    queryFn: () => api.reports.county(fips),
    enabled: !!fips,
  });
};

export const useStateReport = (state) => {
  return useQuery({
    queryKey: ['report', 'state', state],
    queryFn: () => api.reports.state(state),
    enabled: !!state,
  });
};

export const useOutlierReport = () => {
  return useQuery({
    queryKey: ['report', 'outliers'],
    queryFn: () => api.reports.outliers(),
  });
};

export function useCounties(params = {}) {
  return useQuery({
    queryKey: ["counties", params],
    queryFn: () => api.counties(params),
  });
}

export function useOutliers(top = 25) {
  return useQuery({
    queryKey: ["outliers", top],
    queryFn: () => api.outliers(top),
  });
}

export function useAnalytics(key) {
  return useQuery({
    queryKey: ["analytics", key],
    queryFn: () => {
      switch (key) {
        case "correlations": return api.analytics.correlations();
        case "timeseries": return api.analytics.timeseries();
        case "insights": return api.analytics.insights();
        case "quintiles": return api.analytics.quintiles();
        case "disasterTypes": return api.analytics.disasterTypes();
        case "regional": return api.analytics.regional();
        case "underserved": return api.analytics.underserved();
        case "trends": return api.analytics.trends();
        case "model": return api.analytics.model();
        default: throw new Error(`Unknown analytics key: ${key}`);
      }
    },
    staleTime: 60 * 1000 * 5, // 5 minutes
  });
}
