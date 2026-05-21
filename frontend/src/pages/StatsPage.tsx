import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function StatsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: () => api.getStats(),
  });

  if (isLoading) return <div className="p-8 text-slate-600">Loading…</div>;
  if (!data) return <div className="p-8 text-slate-600">No data</div>;

  const retentionPct =
    data.retention_rate !== null ? `${Math.round(data.retention_rate * 100)}%` : null;

  return (
    <div className="max-w-3xl mx-auto p-6 w-full space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Stats</h1>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="text-sm text-slate-500 mb-1">Streak</div>
        <div className="text-3xl font-semibold text-slate-900">{data.streak_days} days</div>
        {data.last_activity && (
          <div className="text-sm text-slate-500 mt-1">
            Last activity: {data.last_activity}
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <h2 className="font-semibold text-slate-900 mb-3">Sessions</h2>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div>
            <div className="text-2xl font-semibold">{data.sessions_total}</div>
            <div className="text-xs text-slate-500">total</div>
          </div>
          <div>
            <div className="text-2xl font-semibold">{data.sessions_last_7d}</div>
            <div className="text-xs text-slate-500">last 7d</div>
          </div>
          <div>
            <div className="text-2xl font-semibold">{data.sessions_last_30d}</div>
            <div className="text-xs text-slate-500">last 30d</div>
          </div>
        </div>
        {Object.keys(data.sessions_by_scenario).length > 0 && (
          <>
            <div className="text-sm text-slate-500 mb-1">By scenario:</div>
            <ul className="text-sm text-slate-700 space-y-1">
              {Object.entries(data.sessions_by_scenario)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <li key={k}>
                    {k}: {v}
                  </li>
                ))}
            </ul>
          </>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <h2 className="font-semibold text-slate-900 mb-3">Cards</h2>
        <div className="text-3xl font-semibold mb-3">{data.cards_total}</div>
        <div className="text-sm text-slate-700">
          Tag:{" "}
          {Object.entries(data.cards_by_tag)
            .map(([k, v]) => `${k} ${v}`)
            .join(" | ")}
        </div>
        <div className="text-sm text-slate-700">
          State: new {data.cards_by_state.new || 0} | learning{" "}
          {data.cards_by_state.learning || 0} | mature {data.cards_by_state.mature || 0}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <h2 className="font-semibold text-slate-900 mb-3">Retention</h2>
        {retentionPct ? (
          <div className="text-2xl font-semibold text-slate-900">
            {retentionPct}
            <span className="text-sm text-slate-500 ml-2">
              ({data.retention_sample_size} mature cards)
            </span>
          </div>
        ) : (
          <div className="text-sm text-slate-600">
            N/A — need ≥5 cards with ≥3 reviews. Have {data.retention_sample_size}.
          </div>
        )}
      </div>
    </div>
  );
}
