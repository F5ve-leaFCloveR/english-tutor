import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ReviewPage", () => {
  it("shows empty state when no sessions", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { getSessions: vi.fn().mockResolvedValue([]) },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
    await waitFor(() => {
      expect(screen.getByText(/no sessions yet/i)).toBeInTheDocument();
    });
  });

  it("renders conversation with inline corrections", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([{
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
        }]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
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
        getSessions: vi.fn().mockResolvedValue([{
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
        }]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
    await waitFor(() => {
      expect(screen.getByText(/analyzing/i)).toBeInTheDocument();
    });
  });

  it("shows clean session message when growth_points is empty", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([{
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
          growth_points: [],
          cards_created: [],
        }]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
    await waitFor(() => {
      expect(screen.getByText(/no corrections found/i)).toBeInTheDocument();
    });
  });
});
