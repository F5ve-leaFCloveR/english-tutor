import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ScenarioSummary, SessionData } from "../api/types";

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

function formatWhen(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const yesterday = new Date(now.getTime() - 86400000);
  const isYesterday = d.toDateString() === yesterday.toDateString();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `Today ${hh}:${mm}`;
  if (isYesterday) return `Yesterday ${hh}:${mm}`;
  const wd = d.toLocaleDateString("en-US", { weekday: "short" });
  const day = d.getDate();
  const month = d.toLocaleDateString("en-US", { month: "short" });
  return `${wd} ${day} ${month} ${hh}:${mm}`;
}

type Status = { label: string; cls: string };

function statusFor(s: SessionData): Status {
  if (s.growth_points_error) return { label: "Error", cls: "bg-red-100 text-red-800" };
  if (!s.growth_points) return { label: "Analyzing", cls: "bg-slate-100 text-slate-700" };
  if (s.growth_points.length === 0) return { label: "Clean", cls: "bg-emerald-100 text-emerald-800" };
  const n = s.growth_points.length;
  return { label: `${n} correction${n === 1 ? "" : "s"}`, cls: "bg-blue-100 text-blue-800" };
}

export function ReviewPage() {
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions-7d"],
    queryFn: () => api.getSessions(50),
  });
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.getScenarios(),
    staleTime: Infinity,
  });

  if (isLoading) {
    return <div className="p-8 text-slate-600">Loading…</div>;
  }

  const cutoff = Date.now() - SEVEN_DAYS_MS;
  const recent = (sessions ?? []).filter(
    (s) => new Date(s.started_at).getTime() >= cutoff,
  );

  if (recent.length === 0) {
    return (
      <div className="p-8 text-center text-slate-600">
        No sessions in the last 7 days. <Link to="/" className="text-blue-600 underline">Run one</Link>.
      </div>
    );
  }

  const scenarioName = (id: string) =>
    scenarios?.find((sc: ScenarioSummary) => sc.id === id)?.name ?? id;

  return (
    <div className="max-w-3xl mx-auto p-6 w-full">
      <h1 className="text-2xl font-semibold mb-4 text-slate-900">Recent sessions</h1>
      <ul className="space-y-2">
        {recent.map((s) => {
          const st = statusFor(s);
          return (
            <li key={s.session_id}>
              <Link
                to={`/review/${s.session_id}`}
                className="block p-3 border border-slate-200 rounded hover:bg-slate-50 transition"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-900 truncate">
                      {scenarioName(s.scenario_id)}
                    </div>
                    <div className="text-xs text-slate-500">{formatWhen(s.started_at)}</div>
                  </div>
                  <span className={`text-xs font-semibold rounded px-2 py-1 whitespace-nowrap ${st.cls}`}>
                    {st.label}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
