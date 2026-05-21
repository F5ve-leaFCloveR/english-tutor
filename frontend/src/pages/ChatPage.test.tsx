import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    // Match the polyfill pattern used by other test files in this project
    // (Layout / VoicePicker / useTTS stub the global because jsdom localStorage
    // can be replaced earlier in the suite — see VoicePicker.test.tsx).
    const store: Record<string, string> = {};
    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: {
        getItem: (k: string) => store[k] ?? null,
        setItem: (k: string, v: string) => { store[k] = v; },
        removeItem: (k: string) => { delete store[k]; },
      },
    });
  });

  it("renders empty state initially", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { chat: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    expect(screen.getByPlaceholderText(/type a message/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start over/i })).toBeInTheDocument();
  });

  it("sends a message and renders reply + correction", async () => {
    vi.resetModules();
    const chatMock = vi.fn().mockResolvedValue({
      reply: "Cool, tell me more!",
      corrections: [{
        tag: "grammar",
        user_utterance: "I readed",
        corrected_version: "I read",
        explanation: "Past tense of read is irregular.",
      }],
    });
    vi.doMock("../api/client", () => ({
      api: { chat: chatMock },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    const input = screen.getByPlaceholderText(/type a message/i);
    fireEvent.change(input, { target: { value: "I readed a book" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("I readed a book")).toBeInTheDocument();
      expect(screen.getByText("Cool, tell me more!")).toBeInTheDocument();
      expect(screen.getByText("I read")).toBeInTheDocument();
      expect(screen.getByText("Past tense of read is irregular.")).toBeInTheDocument();
    });
    expect(chatMock).toHaveBeenCalledTimes(1);
  });

  it("persists messages to localStorage", async () => {
    vi.resetModules();
    const chatMock = vi.fn().mockResolvedValue({ reply: "ok", corrections: [] });
    vi.doMock("../api/client", () => ({
      api: { chat: chatMock },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    const input = screen.getByPlaceholderText(/type a message/i);
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(screen.getByText("ok")).toBeInTheDocument();
    });
    const stored = localStorage.getItem("chat_history");
    expect(stored).not.toBeNull();
    const parsed = JSON.parse(stored!);
    expect(parsed.length).toBeGreaterThan(0);
  });

  it("restores messages from localStorage on mount", async () => {
    localStorage.setItem("chat_history", JSON.stringify([
      { role: "user", content: "prior question", corrections: [] },
      { role: "assistant", content: "prior answer" },
    ]));
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { chat: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    expect(screen.getByText("prior question")).toBeInTheDocument();
    expect(screen.getByText("prior answer")).toBeInTheDocument();
  });

  it("Start over clears state and localStorage", async () => {
    localStorage.setItem("chat_history", JSON.stringify([
      { role: "user", content: "old", corrections: [] },
      { role: "assistant", content: "old reply" },
    ]));
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { chat: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    expect(screen.getByText("old")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start over/i }));
    await waitFor(() => {
      expect(screen.queryByText("old")).not.toBeInTheDocument();
    });
    expect(localStorage.getItem("chat_history")).toBeNull();
  });
});
