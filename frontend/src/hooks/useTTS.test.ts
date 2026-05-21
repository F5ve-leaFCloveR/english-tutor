import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTTS } from "./useTTS";

beforeEach(() => {
  // Stub localStorage
  const store: Record<string, string> = {};
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
    },
  });

  // Stub URL.createObjectURL + revokeObjectURL
  (globalThis as any).URL.createObjectURL = vi.fn(() => "blob:fake");
  (globalThis as any).URL.revokeObjectURL = vi.fn();

  // Stub HTMLAudioElement
  class FakeAudio {
    src = "";
    onended: (() => void) | null = null;
    onerror: ((e: any) => void) | null = null;
    constructor(src: string) { this.src = src; }
    play() {
      // Resolve, then fire onended on next tick
      setTimeout(() => this.onended?.(), 0);
      return Promise.resolve();
    }
  }
  (globalThis as any).Audio = FakeAudio;

  // Stub SpeechSynthesis as fallback
  (globalThis as any).SpeechSynthesisUtterance = vi.fn().mockImplementation(function () {
    return { text: "", onend: null, onerror: null };
  });
  (globalThis as any).speechSynthesis = {
    getVoices: () => [],
    speak: vi.fn((u: any) => setTimeout(() => u.onend?.(), 0)),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
});


describe("useTTS", () => {
  it("speak uses backend TTS by default", async () => {
    vi.mock("../api/client", () => ({
      api: {
        synthesizeTTS: vi.fn().mockResolvedValue(new Blob([new Uint8Array([1, 2])], { type: "audio/wav" })),
      },
      ApiError: class extends Error {},
    }));
    const { api } = await import("../api/client");

    const { result } = renderHook(() => useTTS());
    await act(async () => {
      await result.current.speak("hello world");
    });
    expect((api.synthesizeTTS as any)).toHaveBeenCalledWith("hello world", undefined);
  });

  it("speak passes voice from localStorage", async () => {
    vi.resetModules();
    const synth = vi.fn().mockResolvedValue(new Blob());
    vi.doMock("../api/client", () => ({
      api: { synthesizeTTS: synth },
      ApiError: class extends Error {},
    }));
    const { useTTS: hook } = await import("./useTTS");

    localStorage.setItem("ttsVoice", "nova");
    const { result } = renderHook(() => hook());
    await act(async () => {
      await result.current.speak("hello");
    });
    expect(synth).toHaveBeenCalledWith("hello", "nova");
  });

  it("falls back to SpeechSynthesis on backend error", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { synthesizeTTS: vi.fn().mockRejectedValue(new Error("network")) },
      ApiError: class extends Error {},
    }));
    const { useTTS: hook } = await import("./useTTS");

    const { result } = renderHook(() => hook());
    await act(async () => {
      await result.current.speak("hello");
    });
    expect((globalThis as any).speechSynthesis.speak).toHaveBeenCalled();
  });

  it("exposes static OPENAI_TTS_VOICES as voices", () => {
    const { result } = renderHook(() => useTTS());
    expect(result.current.voices).toContain("alloy");
    expect(result.current.voices.length).toBe(10);
  });
});
