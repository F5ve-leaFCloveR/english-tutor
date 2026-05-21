import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { GrowthPointDict, SessionData } from "../api/types";
import { MessageBubble } from "../components/MessageBubble";
import { InlineCorrection } from "../components/InlineCorrection";

function isAnalyzing(s: SessionData): boolean {
  return !!s.ended_at && !s.growth_points && !s.growth_points_error;
}

function matchGrowthPoints(
  messageText: string,
  pool: GrowthPointDict[],
): { matched: GrowthPointDict[]; remaining: GrowthPointDict[] } {
  const lower = messageText.toLowerCase();
  const matched: GrowthPointDict[] = [];
  const remaining: GrowthPointDict[] = [];
  for (const gp of pool) {
    const needle = gp.user_utterance.toLowerCase().trim();
    if (needle && lower.includes(needle)) {
      matched.push(gp);
    } else {
      remaining.push(gp);
    }
  }
  return { matched, remaining };
}

export function ReviewPage() {
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions-latest"],
    queryFn: () => api.getSessions(1),
    refetchInterval: (q) => {
      const data = q.state.data as SessionData[] | undefined;
      return data && data[0] && isAnalyzing(data[0]) ? 3000 : false;
    },
  });

  if (isLoading) {
    return <div className="p-8 text-slate-600">Loading…</div>;
  }

  const session = sessions?.[0];
  if (!session) {
    return (
      <div className="p-8 text-center text-slate-600">
        No sessions yet. <Link to="/" className="text-blue-600 underline">Run one</Link> to see your review.
      </div>
    );
  }

  if (isAnalyzing(session)) {
    return (
      <div className="p-8 text-center text-slate-600">
        Analyzing your session…
        <div className="mt-3 inline-block w-6 h-6 border-2 border-slate-300 border-t-blue-600 rounded-full animate-spin"></div>
      </div>
    );
  }

  const growthPoints = (session.growth_points ?? []) as GrowthPointDict[];
  const errorMessage = session.growth_points_error;
  let pool = [...growthPoints];

  return (
    <div className="max-w-3xl mx-auto p-6 w-full">
      <h1 className="text-2xl font-semibold mb-4 text-slate-900">Session review</h1>

      {errorMessage && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
          Analysis failed: {errorMessage}
        </div>
      )}

      {growthPoints.length === 0 && !errorMessage && (
        <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded text-sm text-emerald-800">
          No corrections found — clean session!
        </div>
      )}

      <div>
        {session.opening_text && (
          <MessageBubble role="assistant" text={session.opening_text} />
        )}
        {session.turns.map((t, i) => {
          const { matched, remaining } = matchGrowthPoints(t.user_text, pool);
          pool = remaining;
          return (
            <div key={i}>
              <MessageBubble role="user" text={t.user_text} />
              {matched.map((gp, j) => (
                <InlineCorrection key={j} growth_point={gp} />
              ))}
              <MessageBubble role="assistant" text={t.llm_text} />
            </div>
          );
        })}
      </div>

      {pool.length > 0 && (
        <div className="mt-6 border-t pt-4">
          <h2 className="text-sm font-semibold text-slate-700 mb-2">Other corrections</h2>
          {pool.map((gp, i) => <InlineCorrection key={i} growth_point={gp} />)}
        </div>
      )}
    </div>
  );
}
