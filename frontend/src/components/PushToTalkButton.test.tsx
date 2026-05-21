import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PushToTalkButton } from "./PushToTalkButton";

describe("PushToTalkButton", () => {
  it("calls onStart on pointer down and onStop on pointer up", () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    render(<PushToTalkButton onStart={onStart} onStop={onStop} isRecording={false} isBusy={false} />);
    const btn = screen.getByRole("button", { name: /speak/i });
    fireEvent.pointerDown(btn);
    expect(onStart).toHaveBeenCalled();
    fireEvent.pointerUp(btn);
    expect(onStop).toHaveBeenCalled();
  });

  it("shows recording state", () => {
    render(<PushToTalkButton onStart={() => {}} onStop={() => {}} isRecording={true} isBusy={false} />);
    expect(screen.getByText(/release/i)).toBeInTheDocument();
  });

  it("disables button when busy", () => {
    render(<PushToTalkButton onStart={() => {}} onStop={() => {}} isRecording={false} isBusy={true} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
