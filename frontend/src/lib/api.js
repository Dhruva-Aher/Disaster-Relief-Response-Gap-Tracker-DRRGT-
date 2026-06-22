import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

export const api = {
  metrics: async (params = {}) => {
    const res = await apiClient.get("/metrics", { params });
    return res.data;
  },
  counties: async (params = {}) => {
    const res = await apiClient.get("/counties", { params });
    return res.data;
  },
  outliers: async (top = 25) => {
    const res = await apiClient.get("/outliers", { params: { top } });
    return res.data;
  },
  analytics: {
    correlations: async () => (await apiClient.get("/analytics/correlations")).data,
    timeseries: async () => (await apiClient.get("/analytics/timeseries")).data,
    insights: async () => (await apiClient.get("/analytics/insights")).data,
    quintiles: async () => (await apiClient.get("/analytics/quintiles")).data,
    disasterTypes: async () => (await apiClient.get("/analytics/disaster-types")).data,
    regional: async () => (await apiClient.get("/analytics/regional")).data,
    underserved: async () => (await apiClient.get("/analytics/underserved")).data,
    trends: async () => (await apiClient.get("/analytics/trends")).data,
    model: async () => (await apiClient.get("/analytics/model")).data,
  },
  reports: {
    county: async (fips, params = {}) => (await apiClient.get(`/reports/county/${fips}`, { params })).data,
    state: async (state, params = {}) => (await apiClient.get(`/reports/state/${state}`, { params })).data,
    outliers: async (params = {}) => (await apiClient.get("/reports/outliers", { params })).data,
  },
  export: {
    counties: (format = "csv") => `${BASE_URL}/export/counties?format=${format}`,
    outliers: (format = "csv") => `${BASE_URL}/export/outliers?format=${format}`,
    states: (format = "csv") => `${BASE_URL}/export/states?format=${format}`,
    countyReport: (fips, format = "csv") => `${BASE_URL}/reports/county/${fips}?format=${format}`,
    stateReport: (state, format = "csv") => `${BASE_URL}/reports/state/${state}?format=${format}`,
    outlierReport: (format = "csv") => `${BASE_URL}/reports/outliers?format=${format}`,
  }
};
