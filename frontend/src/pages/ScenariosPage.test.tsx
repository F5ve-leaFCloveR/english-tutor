import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ScenariosPage } from "./ScenariosPage";

vi.mock("../api/client", () => ({
  api: {
    getScenarios: vi.fn().mockResolvedValue([
      { id: "tech_interview_behavioral", name: "Tech interview", difficulty: "intermediate" },
      { id: "daily_standup", name: "Daily standup", difficulty: "intermediate" },
    ]),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ScenariosPage", () => {
  it("renders fetched scenarios", async () => {
    render(wrap(<ScenariosPage />));
    await waitFor(() => {
      expect(screen.getByText("Tech interview")).toBeInTheDocument();
      expect(screen.getByText("Daily standup")).toBeInTheDocument();
    });
  });
});
