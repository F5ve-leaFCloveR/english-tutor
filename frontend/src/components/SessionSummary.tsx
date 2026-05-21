import type { GrowthPointDict } from "../api/types";

interface Props {
  growthPoints: GrowthPointDict[];
  cardsCreated: string[];
  error: string | null;
  onClose: () => void;
}

export function SessionSummary({ growthPoints, cardsCreated, error, onClose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-xl w-full max-h-[90vh] overflow-y-auto p-6">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Session complete</h2>
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
            {error}
          </div>
        )}
        {growthPoints.length === 0 && !error && (
          <p className="text-slate-600 mb-4">No growth points this session.</p>
        )}
        {growthPoints.length > 0 && (
          <div className="space-y-4 mb-4">
            <p className="text-sm text-slate-700">
              {cardsCreated.length} cards added for review tomorrow.
            </p>
            {growthPoints.map((gp, i) => (
              <div key={i} className="border-l-4 border-blue-500 pl-3">
                <div className="text-xs text-slate-500 uppercase mb-1">{gp.tag}</div>
                <div className="text-sm text-slate-500 line-through">"{gp.user_utterance}"</div>
                <div className="text-sm text-slate-900 font-medium">"{gp.corrected_version}"</div>
                <div className="text-xs text-slate-600 mt-1">{gp.explanation}</div>
              </div>
            ))}
          </div>
        )}
        <button
          onClick={onClose}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded transition"
        >
          Done
        </button>
      </div>
    </div>
  );
}
