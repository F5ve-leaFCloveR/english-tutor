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

  it("getSessions returns array of sessions", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ sessions: [{ session_id: "s1", turns: [] }] }),
    });
    const sessions = await api.getSessions(5);
    expect(sessions).toHaveLength(1);
    expect(sessions[0].session_id).toBe("s1");
    const call = ((globalThis as any).fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/sessions?limit=5");
  });

  it("chat posts history and message, returns reply + corrections", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        reply: "ok",
        corrections: [{ tag: "grammar", user_utterance: "a", corrected_version: "b", explanation: "e" }],
      }),
    });
    const res = await api.chat([{ role: "user", content: "hi" }], "I goed");
    expect(res.reply).toBe("ok");
    expect(res.corrections).toHaveLength(1);
    const call = ((globalThis as any).fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/chat");
    const body = JSON.parse(call[1].body);
    expect(body.history).toEqual([{ role: "user", content: "hi" }]);
    expect(body.message).toBe("I goed");
  });

  it("createCustomScenario posts payload and returns summary", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "my-talk", name: "My Talk", difficulty: "easy", is_custom: true }),
    });
    const res = await api.createCustomScenario({
      name: "My Talk", difficulty: "easy", system_prompt: "P", opening_line: "Hi",
    });
    expect(res.id).toBe("my-talk");
    const call = ((globalThis as any).fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/scenarios/custom");
    expect(call[1].method).toBe("POST");
    const body = JSON.parse(call[1].body);
    expect(body.name).toBe("My Talk");
    expect(body.system_prompt).toBe("P");
  });

  it("deleteCustomScenario sends DELETE and resolves on 204", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => { throw new Error("204 has no body"); },
    });
    await api.deleteCustomScenario("my-talk");
    const call = ((globalThis as any).fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/scenarios/custom/my-talk");
    expect(call[1].method).toBe("DELETE");
  });

  it("gradeCard supports practice_only flag", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        card_id: "c1", quality: 4, user_attempt_text: "x", target: "y",
        explanation: "z", next_due: "2026-05-23",
      }),
    });
    await api.gradeCard("c1", new Blob(["a"]), false, true);
    const call = ((globalThis as any).fetch as any).mock.calls[0];
    expect(String(call[0])).toContain("/api/review/c1/grade");
    expect(String(call[0])).toContain("practice_only=true");
  });
});

afterAll(() => {
  globalThis.fetch = originalFetch;
});
