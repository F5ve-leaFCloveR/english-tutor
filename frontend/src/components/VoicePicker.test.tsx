import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { VoicePicker } from "./VoicePicker";

beforeEach(() => {
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

vi.mock("../hooks/useTTS", () => ({
  useTTS: () => ({ speak: vi.fn(), isSpeaking: false, voices: ["alloy", "nova", "echo"] }),
}));

describe("VoicePicker", () => {
  it("renders all available voices in select", () => {
    render(<VoicePicker />);
    const sel = screen.getByRole("combobox") as HTMLSelectElement;
    const options = Array.from(sel.options).map(o => o.value);
    expect(options).toContain("alloy");
    expect(options).toContain("nova");
  });

  it("persists choice to localStorage on change", () => {
    render(<VoicePicker />);
    const sel = screen.getByRole("combobox");
    fireEvent.change(sel, { target: { value: "nova" } });
    expect(localStorage.getItem("ttsVoice")).toBe("nova");
  });

  it("renders Test button", () => {
    render(<VoicePicker />);
    expect(screen.getByRole("button", { name: /test/i })).toBeInTheDocument();
  });
});
