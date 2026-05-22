import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionPage } from "./SessionPage";
import { api } from "../api/client";

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
    submitTurn: vi.fn(),
    endSession: vi.fn(),
  },
  ApiError: class extends Error {},
}));

const speakSpy = vi.fn().mockResolvedValue(undefined);
const ttsState: { lastError: string | null } = { lastError: null };
vi.mock("../hooks/useTTS", () => ({
  useTTS: () => ({ speak: speakSpy, isSpeaking: false, voices: [], lastError: ttsState.lastError }),
}));

const recorderState: {
  isRecording: boolean;
  stopRecordingResult: Blob | null;
} = { isRecording: false, stopRecordingResult: null };

vi.mock("../hooks/useRecorder", () => ({
  useRecorder: () => ({
    isRecording: recorderState.isRecording,
    startRecording: vi.fn().mockResolvedValue(undefined),
    stopRecording: vi.fn().mockImplementation(async () => recorderState.stopRecordingResult),
    cancelRecording: vi.fn(),
  }),
}));

beforeEach(() => {
  ttsState.lastError = null;
  recorderState.isRecording = false;
  recorderState.stopRecordingResult = null;
});

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

  it("renders inline corrections under user message after a turn", async () => {
    vi.mocked(api.getSession).mockResolvedValue({
      session_id: "s1",
      scenario_id: "tech_interview_behavioral",
      started_at: "2026-05-21T10:00:00",
      ended_at: null,
      opening_text: "Hi, candidate.",
      turns: [],
    });
    vi.mocked(api.submitTurn).mockResolvedValue({
      user_text: "I goed there",
      assistant_text: "Where?",
      corrections: [
        {
          tag: "grammar",
          user_utterance: "I goed",
          corrected_version: "I went",
          explanation: "Past tense of 'go' is 'went'.",
        },
      ],
    });
    recorderState.stopRecordingResult = new Blob(["fake"], { type: "audio/webm" });

    render(wrap("/session/s1"));

    const pttButton = await screen.findByRole("button", { name: /speak/i });
    fireEvent.pointerDown(pttButton);
    fireEvent.pointerUp(pttButton);

    await waitFor(() => {
      expect(screen.getByText("I goed there")).toBeInTheDocument();
      expect(screen.getByText("I went")).toBeInTheDocument();
      expect(screen.getByText("Past tense of 'go' is 'went'.")).toBeInTheDocument();
    });
  });
});
