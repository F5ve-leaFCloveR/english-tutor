import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PracticePage } from "./PracticePage";

vi.mock("../api/client", () => ({
  api: {
    getDueCards: vi.fn().mockResolvedValue({
      cards: [],
      total_due: 0,
    }),
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

describe("PracticePage", () => {
  it("shows empty state when no due cards", async () => {
    render(wrap(<PracticePage />));
    await waitFor(() => {
      expect(screen.getByText(/no cards due/i)).toBeInTheDocument();
    });
  });
});
