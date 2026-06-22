import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ExplorerPage } from "../pages/ExplorerPage";
import { vi, test, expect } from "vitest";

const queryClient = new QueryClient();

// Mock the hook to avoid actual network requests
vi.mock("../features/api/hooks", () => ({
  useCounties: vi.fn(() => ({
    data: [
      { fips: "123", name: "Test County", state: "TX", median_income: 50000, population: 1000, is_rural: true }
    ],
    isLoading: false
  }))
}));

test("renders ExplorerPage and displays county data", () => {
  render(
    <QueryClientProvider client={queryClient}>
      <ExplorerPage />
    </QueryClientProvider>
  );

  expect(screen.getByText("Test County")).toBeDefined();
  expect(screen.getByText("TX")).toBeDefined();
  expect(screen.getByText("Rural")).toBeDefined();
});
