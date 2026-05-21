import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./Layout";

vi.mock("../api/client", () => ({
  api: {
    getBudget: vi.fn().mockResolvedValue({
      usd_today: 0.01, tokens_today: 100,
      daily_usd_cap: 0.5, daily_token_cap: 200_000,
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

describe("Layout", () => {
  it("renders header with nav links", () => {
    render(wrap(<Layout><div>content</div></Layout>));
    expect(screen.getByText(/scenarios/i)).toBeInTheDocument();
    expect(screen.getByText(/review/i)).toBeInTheDocument();
    expect(screen.getByText(/stats/i)).toBeInTheDocument();
  });
});
