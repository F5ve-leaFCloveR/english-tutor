import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ReviewPage (list)", () => {
  it("shows empty state when no sessions in 7 days", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([]),
        getScenarios: vi.fn().mockResolvedValue([]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage } = await import("./ReviewPage");
    render(wrap(<ReviewPage />));
    await waitFor(() => {
      expect(screen.getByText(/no sessions in the last 7 days/i)).toBeInTheDocument();
    });
  });

  it("filters out sessions older than 7 days", async () => {
    vi.resetModules();
    const now = new Date();
    const today = now.toISOString();
    const tenDaysAgo = new Date(now.getTime() - 10 * 86400000).toISOString();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([
          {
            session_id: "recent", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [], growth_points: [],
          },
          {
            session_id: "old", scenario_id: "tech_interview_behavioral",
            started_at: tenDaysAgo, ended_at: tenDaysAgo,
            opening_text: "Hi.", turns: [], growth_points: [],
          },
        ]),
        getScenarios: vi.fn().mockResolvedValue([
          { id: "tech_interview_behavioral", name: "Behavioral", difficulty: "easy" },
        ]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage } = await import("./ReviewPage");
    render(wrap(<ReviewPage />));
    await waitFor(() => {
      expect(screen.getByText(/behavioral/i)).toBeInTheDocument();
    });
    // The old session shouldn't appear — its link href contains "old".
    const links = screen.getAllByRole("link");
    expect(links.some(l => l.getAttribute("href")?.includes("old"))).toBe(false);
  });

  it("renders each session row with scenario name and status pill", async () => {
    vi.resetModules();
    const today = new Date().toISOString();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([
          {
            session_id: "s1", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [],
            growth_points: [{ tag: "vocab", user_utterance: "x", corrected_version: "y", explanation: "z", context: null }],
          },
          {
            session_id: "s2", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [],
            growth_points: [],
          },
          {
            session_id: "s3", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [],
            // no growth_points field → analyzing
          },
        ]),
        getScenarios: vi.fn().mockResolvedValue([
          { id: "tech_interview_behavioral", name: "Behavioral", difficulty: "easy" },
        ]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage } = await import("./ReviewPage");
    render(wrap(<ReviewPage />));
    await waitFor(() => {
      expect(screen.getByText("1 correction")).toBeInTheDocument(); // s1
      expect(screen.getByText("Clean")).toBeInTheDocument();         // s2
      expect(screen.getByText("Analyzing")).toBeInTheDocument();     // s3
    });
  });
});
