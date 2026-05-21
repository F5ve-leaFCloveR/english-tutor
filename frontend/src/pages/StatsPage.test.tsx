import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatsPage } from "./StatsPage";

vi.mock("../api/client", () => ({
  api: {
    getStats: vi.fn().mockResolvedValue({
      today: "2026-05-21",
      streak_days: 3,
      last_activity: "2026-05-21",
      sessions_total: 12,
      sessions_last_7d: 5,
      sessions_last_30d: 12,
      sessions_by_scenario: { tech_interview_behavioral: 8, daily_standup: 4 },
      cards_total: 47,
      cards_by_tag: { vocab: 28, grammar: 19 },
      cards_by_state: { new: 12, learning: 28, mature: 7 },
      retention_rate: 0.73,
      retention_sample_size: 22,
    }),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("StatsPage", () => {
  it("renders streak, sessions, cards, retention", async () => {
    render(wrap(<StatsPage />));
    await waitFor(() => {
      expect(screen.getByText(/3 days/)).toBeInTheDocument();
      expect(screen.getByText(/47/)).toBeInTheDocument();
      expect(screen.getByText(/73%/)).toBeInTheDocument();
    });
  });
});
