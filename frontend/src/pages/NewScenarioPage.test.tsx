import { describe, it, expect, vi } from "vitest";
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

describe("NewScenarioPage", () => {
  it("renders form with required fields", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { createCustomScenario: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { NewScenarioPage } = await import("./NewScenarioPage");
    render(wrap(<NewScenarioPage />));
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/system prompt/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create/i })).toBeInTheDocument();
  });

  it("submits payload and calls API", async () => {
    vi.resetModules();
    const create = vi.fn().mockResolvedValue({
      id: "my-talk", name: "My Talk", difficulty: "intermediate", is_custom: true,
    });
    vi.doMock("../api/client", () => ({
      api: { createCustomScenario: create },
      ApiError: class extends Error {},
    }));
    const { NewScenarioPage } = await import("./NewScenarioPage");
    render(wrap(<NewScenarioPage />));

    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "My Talk" } });
    fireEvent.change(screen.getByLabelText(/system prompt/i), { target: { value: "You are a friend." } });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith({
        name: "My Talk",
        difficulty: "intermediate",
        system_prompt: "You are a friend.",
        opening_line: "",
      });
    });
  });
});
