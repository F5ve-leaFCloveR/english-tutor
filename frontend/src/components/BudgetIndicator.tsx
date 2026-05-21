import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function BudgetIndicator() {
  const { data } = useQuery({
    queryKey: ["budget"],
    queryFn: () => api.getBudget(),
    refetchInterval: 30_000,
  });
  if (!data) return null;
  const pct = (data.usd_today / data.daily_usd_cap) * 100;
  const color = pct > 80 ? "text-red-600" : pct > 50 ? "text-amber-600" : "text-emerald-700";
  return (
    <span className={`text-sm font-mono ${color}`}>
      ${data.usd_today.toFixed(4)} / ${data.daily_usd_cap.toFixed(2)}
    </span>
  );
}
