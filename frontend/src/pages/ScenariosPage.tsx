import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, Link } from "react-router-dom";
import { api } from "../api/client";

export function ScenariosPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { data: scenarios, isLoading } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.getScenarios(),
  });
  const startMutation = useMutation({
    mutationFn: (id: string) => api.startSession(id),
    onSuccess: (result) => {
      navigate(`/session/${result.session_id}`, { state: { opening: result.opening_text } });
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteCustomScenario(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["scenarios"] }),
  });

  if (isLoading) return <div className="p-8 text-slate-600">Loading scenarios…</div>;

  return (
    <div className="max-w-2xl mx-auto p-8 w-full">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-semibold text-slate-900">Pick a scenario</h1>
        <Link to="/scenarios/new" className="text-sm text-blue-600 hover:underline">+ Create scenario</Link>
      </div>
      <div className="space-y-3">
        {scenarios?.map((s) => (
          <div
            key={s.id}
            className="flex items-stretch border border-slate-200 rounded-lg bg-white hover:border-slate-400 transition"
          >
            <button
              onClick={() => startMutation.mutate(s.id)}
              disabled={startMutation.isPending || deleteMutation.isPending}
              className="flex-1 text-left p-4 disabled:opacity-50"
            >
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-900">{s.name}</span>
                {s.is_custom && (
                  <span className="text-xs px-1.5 py-0.5 bg-purple-100 text-purple-800 rounded">custom</span>
                )}
              </div>
              <div className="text-sm text-slate-500 mt-1">Difficulty: {s.difficulty}</div>
            </button>
            {s.is_custom && (
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  if (confirm(`Delete "${s.name}"?`)) {
                    deleteMutation.mutate(s.id);
                  }
                }}
                disabled={deleteMutation.isPending}
                className="px-3 text-slate-400 hover:text-red-500 disabled:opacity-50"
                aria-label={`Delete ${s.name}`}
              >
                ×
              </button>
            )}
          </div>
        ))}
      </div>
      {startMutation.isError && (
        <div className="mt-4 text-red-600 text-sm">
          Failed to start: {(startMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}
