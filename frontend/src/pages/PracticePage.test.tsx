import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PracticePage } from "./PracticePage";

vi.mock("../api/client", () => ({
  api: {
    getDueCards: vi.fn().mockResolvedValue({
      cards: [],
      total_due: 0,
    }),
    getStats: vi.fn().mockResolvedValue({
      today: "2026-05-21",
      streak_days: 0,
      last_activity: null,
      sessions_total: 0,
      sessions_last_7d: 0,
      sessions_last_30d: 0,
      sessions_by_scenario: {},
      cards_total: 0,
      cards_by_tag: {},
      cards_by_state: {},
      retention_rate: null,
      retention_sample_size: 0,
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

describe("PracticePage", () => {
  it("shows empty state when no due cards and no cards exist yet", async () => {
    render(wrap(<PracticePage />));
    await waitFor(() => {
      expect(screen.getByText(/no cards yet/i)).toBeInTheDocument();
      expect(screen.getByText(/cards become reviewable the next day/i)).toBeInTheDocument();
    });
  });

  it("hints about +1 day delay when cards exist but none due today", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getStats).mockResolvedValueOnce({
      today: "2026-05-21",
      streak_days: 0,
      last_activity: "2026-05-21",
      sessions_total: 1,
      sessions_last_7d: 1,
      sessions_last_30d: 1,
      sessions_by_scenario: {},
      cards_total: 19,
      cards_by_tag: {},
      cards_by_state: {},
      retention_rate: null,
      retention_sample_size: 0,
    });
    render(wrap(<PracticePage />));
    await waitFor(() => {
      expect(screen.getByText(/no cards due today/i)).toBeInTheDocument();
      expect(screen.getByText(/all 19 cards are scheduled for later/i)).toBeInTheDocument();
      expect(screen.getByText(/\+1 day/i)).toBeInTheDocument();
    });
  });
});
