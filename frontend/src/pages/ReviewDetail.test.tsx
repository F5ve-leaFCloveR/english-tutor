import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

function wrap(node: ReactNode, initialPath = "/review/s1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/review/:sessionId" element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ReviewDetail", () => {
  it("renders conversation with inline corrections", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSession: vi.fn().mockResolvedValue({
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [
            { ts: "...", user_text: "I made a project yesterday",
              llm_text: "What kind of project?" },
          ],
          growth_points: [{
            tag: "vocab",
            user_utterance: "I made a project",
            corrected_version: "I led a project",
            explanation: "Led signals ownership.",
            context: null,
          }],
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
    await waitFor(() => {
      expect(screen.getByText("I made a project yesterday")).toBeInTheDocument();
      expect(screen.getByText("I led a project")).toBeInTheDocument();
      expect(screen.getByText("Led signals ownership.")).toBeInTheDocument();
    });
  });

  it("shows analyzing state when growth_points missing", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSession: vi.fn().mockResolvedValue({
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
    await waitFor(() => {
      expect(screen.getByText(/analyzing/i)).toBeInTheDocument();
    });
  });

  it("shows clean session message when growth_points is empty", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSession: vi.fn().mockResolvedValue({
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
          growth_points: [],
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
    await waitFor(() => {
      expect(screen.getByText(/no corrections found/i)).toBeInTheDocument();
    });
  });

  it("shows error banner when growth_points_error is set", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSession: vi.fn().mockResolvedValue({
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
          growth_points_error: "rate_limit",
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
    await waitFor(() => {
      expect(screen.getByText(/analysis failed: rate_limit/i)).toBeInTheDocument();
    });
  });
});
