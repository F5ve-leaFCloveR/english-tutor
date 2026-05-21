import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { InlineCorrection } from "./InlineCorrection";

describe("InlineCorrection", () => {
  const gp = {
    tag: "vocab" as const,
    user_utterance: "I made a project",
    corrected_version: "I led a project",
    explanation: "Led signals ownership.",
    context: null,
  };

  it("renders tag, original, corrected, explanation", () => {
    render(<InlineCorrection growth_point={gp} />);
    expect(screen.getByText(/vocab/i)).toBeInTheDocument();
    expect(screen.getByText("I made a project")).toBeInTheDocument();
    expect(screen.getByText("I led a project")).toBeInTheDocument();
    expect(screen.getByText("Led signals ownership.")).toBeInTheDocument();
  });

  it("renders strikethrough on original utterance", () => {
    render(<InlineCorrection growth_point={gp} />);
    const orig = screen.getByText("I made a project");
    expect(orig.tagName.toLowerCase()).toBe("s");
  });
});
