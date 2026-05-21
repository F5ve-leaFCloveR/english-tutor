import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTTS } from "./useTTS";

beforeEach(() => {
  const mockUtterance: any = { text: "", voice: null, onend: null, onerror: null };
  (globalThis as any).SpeechSynthesisUtterance = vi.fn(() => mockUtterance);
  (globalThis as any).speechSynthesis = {
    getVoices: () => [{ name: "Voice A" }],
    speak: vi.fn((u: any) => {
      setTimeout(() => u.onend?.(), 0);
    }),
    cancel: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
  // jsdom in vitest may not expose localStorage as a function-bearing object —
  // stub a minimal in-memory implementation.
  const store: Record<string, string> = {};
  (globalThis as any).localStorage = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => {
      store[k] = v;
    },
    removeItem: (k: string) => {
      delete store[k];
    },
    clear: () => {
      for (const k of Object.keys(store)) delete store[k];
    },
  };
});

describe("useTTS", () => {
  it("speak resolves on utterance end", async () => {
    const { result } = renderHook(() => useTTS());
    await act(async () => {
      await result.current.speak("hello");
    });
    expect((globalThis as any).speechSynthesis.speak).toHaveBeenCalled();
  });

  it("exposes available voices", () => {
    const { result } = renderHook(() => useTTS());
    expect(result.current.voices.length).toBeGreaterThan(0);
  });
});
