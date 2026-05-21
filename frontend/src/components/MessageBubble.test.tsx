import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";

describe("MessageBubble", () => {
  it("renders user bubble with right alignment", () => {
    const { container } = render(<MessageBubble role="user" text="hi" />);
    expect(screen.getByText("hi")).toBeInTheDocument();
    expect(container.querySelector(".justify-end")).toBeInTheDocument();
  });

  it("renders assistant bubble with left alignment", () => {
    const { container } = render(<MessageBubble role="assistant" text="hello" />);
    expect(container.querySelector(".justify-start")).toBeInTheDocument();
  });

  it("shows speaking indicator when isSpeaking is true", () => {
    render(<MessageBubble role="assistant" text="hi" isSpeaking />);
    expect(screen.getByText(/📢/)).toBeInTheDocument();
  });
});
