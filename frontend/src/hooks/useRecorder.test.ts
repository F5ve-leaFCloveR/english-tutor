import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRecorder } from "./useRecorder";

beforeEach(() => {
  // Mock MediaRecorder
  const mockStream = { getTracks: () => [] };
  (globalThis as any).navigator.mediaDevices = {
    getUserMedia: vi.fn().mockResolvedValue(mockStream),
  };

  class MockMediaRecorder {
    state = "inactive";
    mimeType = "audio/webm";
    ondataavailable: ((e: any) => void) | null = null;
    onstop: (() => void) | null = null;
    constructor(_: any) {}
    start() {
      this.state = "recording";
    }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["x"], { type: "audio/webm" }) });
      this.onstop?.();
    }
    static isTypeSupported(_: string) {
      return true;
    }
  }
  (globalThis as any).MediaRecorder = MockMediaRecorder;
});

describe("useRecorder", () => {
  it("starts and stops recording, returns blob", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.startRecording();
    });
    expect(result.current.isRecording).toBe(true);

    // Advance time so duration > MIN_DURATION_MS (500)
    await new Promise((r) => setTimeout(r, 600));

    let blob: Blob | null = null;
    await act(async () => {
      blob = await result.current.stopRecording();
    });
    expect(result.current.isRecording).toBe(false);
    expect(blob).toBeInstanceOf(Blob);
  });

  it("cancelRecording discards blob", async () => {
    const { result } = renderHook(() => useRecorder());
    await act(async () => {
      await result.current.startRecording();
    });
    act(() => {
      result.current.cancelRecording();
    });
    expect(result.current.isRecording).toBe(false);
  });
});
