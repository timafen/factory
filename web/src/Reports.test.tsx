import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi, test, expect } from "vitest";
import { api } from "./api";
import { Reports } from "./Reports";

test("ready report has a download while failed report explains why", async () => {
  vi.spyOn(api, "dailyReports").mockResolvedValue([
    { report_date: "2026-08-12", timezone: "America/Chicago", status: "ready" },
    { report_date: "2026-08-11", timezone: "America/Chicago", status: "error", error: "Chromium недоступен" },
  ]);
  render(<QueryClientProvider client={new QueryClient()}><Reports /></QueryClientProvider>);
  expect(await screen.findByRole("link", { name: "Скачать PDF" })).toHaveAttribute("href", "/api/v1/reports/daily/2026-08-12/pdf?timezone=America%2FChicago");
  expect(screen.getByText(/Chromium недоступен/)).toBeInTheDocument();
});
