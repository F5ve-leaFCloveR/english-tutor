import type {
  BudgetSummary,
  DueCardsResult,
  EndSessionAccepted,
  GradeResult,
  ScenarioSummary,
  SessionData,
  StartSessionResult,
  StatsSummary,
  TurnResult,
  ApiErrorBody,
} from "./types";

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.error || "API error");
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let body: ApiErrorBody;
    try {
      body = await res.json();
    } catch {
      body = { error: "unknown_error" };
    }
    throw new ApiError(res.status, body);
  }
  return res.json();
}

export const api = {
  async getScenarios(): Promise<ScenarioSummary[]> {
    const data = await request<{ scenarios: ScenarioSummary[] }>("/api/scenarios");
    return data.scenarios;
  },

  startSession(scenario_id: string): Promise<StartSessionResult> {
    return request("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_id }),
    });
  },

  getSession(session_id: string): Promise<SessionData> {
    return request(`/api/sessions/${session_id}`);
  },

  submitTurn(session_id: string, audio: Blob): Promise<TurnResult> {
    const form = new FormData();
    form.append("audio", audio, "turn.webm");
    return request(`/api/sessions/${session_id}/turn`, { method: "POST", body: form });
  },

  endSession(session_id: string): Promise<EndSessionAccepted> {
    return request(`/api/sessions/${session_id}/end`, { method: "POST" });
  },

  async synthesizeTTS(text: string, voice?: string): Promise<Blob> {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
    });
    if (!res.ok) {
      let body: ApiErrorBody;
      try {
        body = await res.json();
      } catch {
        body = { error: "tts_failed" };
      }
      throw new ApiError(res.status, body);
    }
    return res.blob();
  },

  getDueCards(params: { limit?: number; tag?: string } = {}): Promise<DueCardsResult> {
    const qs = new URLSearchParams();
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.tag) qs.set("tag", params.tag);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request(`/api/review/due${suffix}`);
  },

  gradeCard(card_id: string, audio: Blob | null, skip: boolean): Promise<GradeResult> {
    if (skip) {
      const form = new FormData();
      form.append("skip", "true");
      return request(`/api/review/${card_id}/grade?skip=true`, {
        method: "POST",
        body: form,
      });
    }
    const form = new FormData();
    if (audio) form.append("audio", audio, "grade.webm");
    return request(`/api/review/${card_id}/grade`, { method: "POST", body: form });
  },

  getStats(days?: number): Promise<StatsSummary> {
    const qs = days !== undefined ? `?days=${days}` : "";
    return request(`/api/stats${qs}`);
  },

  getBudget(): Promise<BudgetSummary> {
    return request("/api/budget");
  },

  async getSessions(limit: number = 10): Promise<SessionData[]> {
    const data = await request<{ sessions: SessionData[] }>(`/api/sessions?limit=${limit}`);
    return data.sessions;
  },
};
