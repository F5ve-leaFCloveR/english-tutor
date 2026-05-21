import { describe, it, expect, vi, beforeEach, afterAll } from "vitest";
import { api } from "./client";

const originalFetch = globalThis.fetch;

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("getScenarios returns parsed scenarios array", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scenarios: [{ id: "x", name: "X", difficulty: "y" }] }),
    });
    const result = await api.getScenarios();
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("x");
  });

  it("startSession POSTs scenario_id and returns result", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ session_id: "s1", opening_text: "Hi" }),
    });
    const result = await api.startSession("x");
    expect(result.session_id).toBe("s1");
    expect(result.opening_text).toBe("Hi");
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[1].method).toBe("POST");
    const body = JSON.parse(call[1].body);
    expect(body.scenario_id).toBe("x");
  });

  it("submitTurn POSTs multipart audio", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ user_text: "hi", assistant_text: "hello" }),
    });
    const blob = new Blob(["fake"], { type: "audio/webm" });
    await api.submitTurn("s1", blob);
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(call[1].body).toBeInstanceOf(FormData);
  });

  it("throws ApiError on non-ok response", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: "scenario_not_found" }),
    });
    await expect(api.startSession("bogus")).rejects.toThrow();
  });

  it("synthesizeTTS POSTs JSON and returns Blob", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: "audio/wav" }),
    });
    const blob = await api.synthesizeTTS("hello", "nova");
    expect(blob).toBeInstanceOf(Blob);
    const call = ((globalThis as any).fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/tts");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ text: "hello", voice: "nova" });
  });

  it("endSession returns EndSessionAccepted shape", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ session_id: "s1", status: "processing" }),
    });
    const r = await api.endSession("s1");
    expect(r.session_id).toBe("s1");
    expect(r.status).toBe("processing");
  });
});

afterAll(() => {
  globalThis.fetch = originalFetch;
});
