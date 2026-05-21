import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export function ScenariosPage() {
  const navigate = useNavigate();
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

  if (isLoading) return <div className="p-8 text-slate-600">Loading scenarios…</div>;

  return (
    <div className="max-w-2xl mx-auto p-8 w-full">
      <h1 className="text-2xl font-semibold mb-6 text-slate-900">Pick a scenario</h1>
      <div className="space-y-3">
        {scenarios?.map((s) => (
          <button
            key={s.id}
            onClick={() => startMutation.mutate(s.id)}
            disabled={startMutation.isPending}
            className="w-full text-left border border-slate-200 rounded-lg p-4 bg-white hover:border-slate-400 transition disabled:opacity-50"
          >
            <div className="font-medium text-slate-900">{s.name}</div>
            <div className="text-sm text-slate-500 mt-1">Difficulty: {s.difficulty}</div>
          </button>
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
