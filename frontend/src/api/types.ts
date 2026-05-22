export interface ScenarioSummary {
  id: string;
  name: string;
  difficulty: string;
  is_custom?: boolean;
}

export interface StartSessionResult {
  session_id: string;
  opening_text: string;
}

export interface TurnResult {
  user_text: string;
  assistant_text: string;
  corrections: ChatCorrectionDict[];
}

export interface SessionData {
  session_id: string;
  scenario_id: string;
  started_at: string;
  ended_at: string | null;
  opening_text: string | null;
  turns: Array<{ ts: string; user_text: string; llm_text: string; corrections?: ChatCorrectionDict[] }>;
  growth_points?: GrowthPointDict[];
  cards_created?: string[];
  growth_points_error?: string | null;
}

export interface GrowthPointDict {
  tag: "vocab" | "grammar";
  user_utterance: string;
  corrected_version: string;
  explanation: string;
  context: string | null;
}

export interface EndSessionResult {
  session_id: string;
  ended_at: string | null;
  growth_points: GrowthPointDict[];
  cards_created: string[];
  growth_points_error: string | null;
}

export interface Card {
  id: string;
  created_from_session_id: string;
  tag: "vocab" | "grammar";
  user_utterance: string;
  corrected_version: string;
  explanation: string;
  context: string | null;
  ease_factor: number;
  interval_days: number;
  repetitions: number;
  due_date: string;
  last_review_quality: number | null;
  review_history: Array<{ date: string; quality: number }>;
}

export interface DueCardsResult {
  cards: Card[];
  total_due: number;
}

export interface GradeResult {
  card_id: string;
  user_attempt_text: string;
  quality: number;
  target: string;
  explanation: string;
  next_due: string;
}

export interface BudgetSummary {
  usd_today: number;
  tokens_today: number;
  daily_usd_cap: number;
  daily_token_cap: number;
}

export interface StatsSummary {
  today: string;
  streak_days: number;
  last_activity: string | null;
  sessions_total: number;
  sessions_last_7d: number;
  sessions_last_30d: number;
  sessions_by_scenario: Record<string, number>;
  cards_total: number;
  cards_by_tag: Record<string, number>;
  cards_by_state: Record<string, number>;
  retention_rate: number | null;
  retention_sample_size: number;
}

export interface ApiErrorBody {
  error: string;
  message?: string;
  [key: string]: unknown;
}

export interface EndSessionAccepted {
  session_id: string;
  status: "processing";
}

export const OPENAI_TTS_VOICES = [
  "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar",
] as const;

export type OpenAITTSVoice = typeof OPENAI_TTS_VOICES[number];

export interface ChatMessageDict {
  role: "user" | "assistant";
  content: string;
}

export interface ChatCorrectionDict {
  tag: "vocab" | "grammar";
  user_utterance: string;
  corrected_version: string;
  explanation: string;
}

export interface ChatResponseDict {
  reply: string;
  corrections: ChatCorrectionDict[];
}

export interface CustomScenarioCreate {
  name: string;
  difficulty: string;
  system_prompt: string;
  opening_line?: string;
}
