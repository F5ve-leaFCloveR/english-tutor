import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";

export function NewScenarioPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [difficulty, setDifficulty] = useState("intermediate");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [openingLine, setOpeningLine] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !systemPrompt.trim()) {
      setError("Name and system prompt are required.");
      return;
    }
    setSubmitting(true);
    try {
      await api.createCustomScenario({
        name: name.trim(),
        difficulty,
        system_prompt: systemPrompt.trim(),
        opening_line: openingLine.trim(),
      });
      navigate("/");
    } catch (e) {
      const msg = e instanceof ApiError
        ? (e.body?.message as string) || (e.body?.error as string) || "Failed"
        : (e as Error).message;
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6 w-full">
      <h1 className="text-2xl font-semibold mb-4 text-slate-900">New custom scenario</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label htmlFor="scenario-name" className="block text-sm font-medium text-slate-700 mb-1">Name</label>
          <input
            id="scenario-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Talk to a barber"
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="scenario-difficulty" className="block text-sm font-medium text-slate-700 mb-1">Difficulty</label>
          <select
            id="scenario-difficulty"
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className="border border-slate-300 rounded px-3 py-2 text-sm bg-white"
          >
            <option value="easy">easy</option>
            <option value="intermediate">intermediate</option>
            <option value="advanced">advanced</option>
          </select>
        </div>
        <div>
          <label htmlFor="scenario-prompt" className="block text-sm font-medium text-slate-700 mb-1">System prompt</label>
          <textarea
            id="scenario-prompt"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="Describe the bot's role, behavior, and any constraints. Example: 'You are a friendly barber in NYC. Keep responses casual and short.'"
            rows={8}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="scenario-opening" className="block text-sm font-medium text-slate-700 mb-1">Opening line (optional)</label>
          <textarea
            id="scenario-opening"
            value={openingLine}
            onChange={(e) => setOpeningLine(e.target.value)}
            placeholder="What the bot says first. If left empty, a default opener is used."
            rows={2}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">{error}</div>
        )}
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-6 py-2 rounded text-sm font-medium"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/")}
            className="text-slate-600 hover:text-slate-900 text-sm"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
