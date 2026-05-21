import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionPage } from "./SessionPage";

vi.mock("../api/client", () => ({
  api: {
    getSession: vi.fn().mockResolvedValue({
      session_id: "s1",
      scenario_id: "tech_interview_behavioral",
      started_at: "2026-05-21T10:00:00",
      ended_at: null,
      opening_text: "Hi, tell me about yourself.",
      turns: [],
    }),
  },
  ApiError: class extends Error {},
}));

const speakSpy = vi.fn().mockResolvedValue(undefined);
const ttsState: { lastError: string | null } = { lastError: null };
vi.mock("../hooks/useTTS", () => ({
  useTTS: () => ({ speak: speakSpy, isSpeaking: false, voices: [], lastError: ttsState.lastError }),
}));

beforeEach(() => {
  ttsState.lastError = null;
});

vi.mock("../hooks/useRecorder", () => ({
  useRecorder: () => ({
    isRecording: false, startRecording: vi.fn(), stopRecording: vi.fn(), cancelRecording: vi.fn(),
  }),
}));

function wrap(initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/session/:id" element={<SessionPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("SessionPage", () => {
  it("renders opening text as assistant bubble", async () => {
    render(wrap("/session/s1"));
    await waitFor(() => {
      expect(screen.getByText("Hi, tell me about yourself.")).toBeInTheDocument();
    });
  });

  it("auto-plays opening via TTS on mount", async () => {
    speakSpy.mockClear();
    render(wrap("/session/s1"));
    await waitFor(() => {
      expect(speakSpy).toHaveBeenCalledWith("Hi, tell me about yourself.");
    });
  });

  it("shows TTS error banner when lastError is set", async () => {
    ttsState.lastError = "Audio reservation $0.50 required";
    render(wrap("/session/s1"));
    await waitFor(() => {
      expect(screen.getByText(/TTS error.*0\.50/i)).toBeInTheDocument();
    });
  });
});
