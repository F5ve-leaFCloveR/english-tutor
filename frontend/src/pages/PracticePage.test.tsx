import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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
    gradeCard: vi.fn(),
  },
}));

vi.mock("../hooks/useTTS", () => ({
  useTTS: () => ({ speak: vi.fn().mockResolvedValue(undefined), stop: vi.fn(), isSpeaking: false }),
}));

vi.mock("../hooks/useRecorder", () => ({
  useRecorder: () => ({
    isRecording: false,
    startRecording: vi.fn().mockResolvedValue(undefined),
    stopRecording: vi.fn().mockResolvedValue(new Blob(["x"], { type: "audio/webm" })),
    cancelRecording: vi.fn(),
  }),
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

  it("shows Try again button alongside Next card after grading; Try again resets to recorder UI", async () => {
    const { api } = await import("../api/client");
    vi.mocked(api.getDueCards).mockResolvedValueOnce({
      cards: [
        {
          id: "card-1",
          target: "How are you?",
          context: "greeting",
          tags: ["grammar"],
          source_session_id: "s1",
          created_at: "2026-05-20T00:00:00Z",
          due: "2026-05-21T00:00:00Z",
          state: "new",
          interval_days: 0,
          ease_factor: 2.5,
          repetitions: 0,
        } as never,
      ],
      total_due: 1,
    });
    vi.mocked(api.gradeCard).mockResolvedValueOnce({
      card_id: "card-1",
      quality: 4,
      target: "How are you?",
      user_attempt_text: "how are you",
      explanation: "Good job.",
      next_due: "2026-05-22T00:00:00Z",
      interval_days: 1,
      ease_factor: 2.5,
      repetitions: 1,
      state: "review",
    } as never);

    render(wrap(<PracticePage />));
    // Trigger the push-to-talk flow: find the recorder button and simulate pointer events.
    const recordBtn = await screen.findByRole("button", { name: /press and hold to speak/i });
    fireEvent.pointerDown(recordBtn);
    fireEvent.pointerUp(recordBtn);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /try again/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /next card/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));

    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /next card/i })).not.toBeInTheDocument();
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
