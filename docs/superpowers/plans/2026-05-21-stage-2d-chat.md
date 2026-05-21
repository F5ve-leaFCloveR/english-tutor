# Stage 2d — Free Chat with Per-Message Corrections — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Free-form text chat with the bot at a new `/chat` route. After each user message, the bot replies AND analyzes the user's text for vocab/grammar corrections, rendered inline under the user message (`InlineCorrection` from Stage 2c). "Start over" button clears the conversation. Chat persists in `localStorage` so reload survives, but isn't stored on the backend; clearing cache/cookies wipes it.

**Architecture:** Single new stateless endpoint `POST /api/chat`. One LLM call per turn returns `{ reply, corrections }` in structured JSON (same `GrowthPointDict` shape as session growth_points → `InlineCorrection` reused). No backend storage, no SRS card creation, no async background work.

**Tech Stack:** Same as Stage 2c. No new deps.

**Prerequisites:**
- Stage 2c.2 (commit `1168546` or later) on `main`.
- All current tests green: 180 pytest, 42 vitest, build succeeds.

---

## File Structure

```
tutor/
├── conversation.py            (NEW: ChatTurn class — prompt, parse, retry)
└── web/
    ├── schemas.py             (MODIFY: ChatRequest, ChatResponse, ChatMessage)
    ├── services.py            (MODIFY: chat_service)
    └── api.py                 (MODIFY: POST /api/chat)

tests/
├── test_conversation.py       (NEW)
└── web/
    └── test_chat.py           (NEW: route + service)

frontend/src/
├── api/
│   ├── client.ts              (MODIFY: api.chat)
│   ├── client.test.ts         (MODIFY: + chat test)
│   └── types.ts               (MODIFY: ChatMessage, ChatResponse)
├── pages/
│   ├── ChatPage.tsx           (NEW)
│   └── ChatPage.test.tsx      (NEW)
├── components/
│   ├── Layout.tsx             (MODIFY: + Chat link)
│   └── Layout.test.tsx        (MODIFY: + Chat assertion)
└── App.tsx                    (MODIFY: + /chat route)
```

---

## Task 1: `ChatTurn` — prompt, schema, parse, retry

**Files:**
- Create: `tutor/conversation.py`
- Create: `tests/test_conversation.py`

- [ ] **Step 1: Write failing tests** `tests/test_conversation.py`:

```python
import json
from unittest.mock import MagicMock
import pytest


def test_chat_turn_returns_reply_and_corrections():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({
        "reply": "That's interesting! What kind of book?",
        "corrections": [
            {
                "tag": "grammar",
                "user_utterance": "I readed a book",
                "corrected_version": "I read a book",
                "explanation": "Past tense of 'read' is irregular; same spelling, different pronunciation."
            }
        ],
    })
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="I readed a book yesterday")
    assert res.reply == "That's interesting! What kind of book?"
    assert len(res.corrections) == 1
    assert res.corrections[0].tag == "grammar"
    assert res.corrections[0].corrected_version == "I read a book"


def test_chat_turn_caps_corrections_at_three():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({
        "reply": "ok",
        "corrections": [
            {"tag": "vocab", "user_utterance": "u1", "corrected_version": "c1", "explanation": "e1"},
            {"tag": "vocab", "user_utterance": "u2", "corrected_version": "c2", "explanation": "e2"},
            {"tag": "vocab", "user_utterance": "u3", "corrected_version": "c3", "explanation": "e3"},
            {"tag": "vocab", "user_utterance": "u4", "corrected_version": "c4", "explanation": "e4"},
            {"tag": "vocab", "user_utterance": "u5", "corrected_version": "c5", "explanation": "e5"},
        ],
    })
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert len(res.corrections) == 3


def test_chat_turn_empty_corrections_ok():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"reply": "Cool!", "corrections": []})
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="Hello there.")
    assert res.reply == "Cool!"
    assert res.corrections == []


def test_chat_turn_retries_on_invalid_json_then_succeeds():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.side_effect = [
        "Sorry, here's my answer: " + "not json",  # first attempt
        json.dumps({"reply": "ok", "corrections": []}),  # retry
    ]
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert res.reply == "ok"
    assert llm.complete.call_count == 2


def test_chat_turn_returns_fallback_after_two_failures():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = "still not json"
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert res.reply  # non-empty fallback string
    assert res.corrections == []


def test_chat_turn_strips_code_fences():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = "```json\n" + json.dumps({"reply": "hi", "corrections": []}) + "\n```"
    chat = ChatTurn(llm=llm, model="m")
    res = chat.respond(history=[], message="hi")
    assert res.reply == "hi"


def test_chat_turn_includes_history_in_llm_call():
    from tutor.conversation import ChatTurn

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    chat = ChatTurn(llm=llm, model="m")
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How are you?"},
    ]
    chat.respond(history=history, message="I am fine")

    call_kwargs = llm.complete.call_args.kwargs
    messages = call_kwargs["messages"]
    # First is system prompt
    assert messages[0]["role"] == "system"
    # Then the history (2 messages)
    assert messages[1] == {"role": "user", "content": "Hello"}
    assert messages[2] == {"role": "assistant", "content": "Hi! How are you?"}
    # Last is the new user message
    assert messages[-1] == {"role": "user", "content": "I am fine"}
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest tests/test_conversation.py -v` → all fail (module not found).

- [ ] **Step 3: Implement `tutor/conversation.py`**:

```python
"""Free-chat LLM turn: reply + per-message corrections in one structured call."""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from tutor.llm import LLMClient

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a friendly English conversational partner for a Russian-native intermediate student.

Your job each turn:
1. Reply naturally and conversationally in 2-4 sentences. Match the user's tone. Ask follow-up questions when natural.
2. Identify up to 3 corrections to the user's MOST RECENT message only. Focus on:
   - vocab: word choice that's correct but weak/generic. Suggest a stronger, more precise word.
   - grammar: tense, articles, prepositions, word order errors.
   Skip filler words, typos, idiom/register issues, minor style preferences. If the message is clean, return an empty list.

Return STRICT JSON, no commentary:
{
  "reply": "<your conversational reply>",
  "corrections": [
    {
      "tag": "vocab" | "grammar",
      "user_utterance": "<verbatim what the user wrote>",
      "corrected_version": "<your improved version>",
      "explanation": "<1-2 sentences why the correction is better>"
    }
  ]
}
"""


_FALLBACK_REPLY = "Sorry, I had trouble responding. Could you say that again?"


class ChatCorrection(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str


class ChatResponse(BaseModel):
    reply: str
    corrections: list[ChatCorrection]


class ChatTurn:
    def __init__(self, llm: LLMClient, model: str) -> None:
        self._llm = llm
        self._model = model

    def respond(
        self,
        history: list[dict[str, str]],
        message: str,
    ) -> ChatResponse:
        """One turn: LLM replies AND returns corrections for the latest user message."""
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        reminder = {
            "role": "user",
            "content": (
                "Your previous response was not valid JSON. Return STRICT JSON only, "
                "no commentary, no markdown fences. Just the {\"reply\": ..., \"corrections\": [...]} object."
            ),
        }

        last_error: Exception | None = None
        for attempt in range(2):
            call_messages = messages if attempt == 0 else messages + [reminder]
            try:
                raw = self._llm.complete(
                    messages=call_messages,
                    temperature=0.7,
                    model_override=self._model,
                    max_tokens=1024,
                )
            except Exception as e:
                log.warning("Chat LLM call failed: %s", e)
                return ChatResponse(reply=_FALLBACK_REPLY, corrections=[])
            try:
                parsed = ChatResponse.model_validate_json(_strip_code_fences(raw))
                parsed.corrections = parsed.corrections[:3]
                return parsed
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                log.warning("Chat returned invalid JSON (attempt %d): %s", attempt + 1, e)
                continue

        log.warning("Chat exhausted retries: %s", last_error)
        return ChatResponse(reply=_FALLBACK_REPLY, corrections=[])


def _strip_code_fences(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ```. Strip if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_conversation.py -v
```
→ 7 green.

```bash
git add tutor/conversation.py tests/test_conversation.py
git commit -m "feat(chat): ChatTurn — reply + per-message corrections in one LLM call"
```

## Context

- Branch: `main`. Previous: `1168546`.
- Task 1 of 6.

---

## Task 2: Backend chat route + service + schemas

**Files:**
- Modify: `tutor/web/schemas.py`
- Modify: `tutor/web/services.py`
- Modify: `tutor/web/api.py`
- Modify: `tutor/web/deps.py` (add chat_model field)
- Create: `tests/web/test_chat.py`

- [ ] **Step 1: Add schemas** to `tutor/web/schemas.py`:

```python
class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    history: list[ChatMessage] = []
    message: str


class ChatCorrectionDict(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str


class ChatResponseDict(BaseModel):
    reply: str
    corrections: list[ChatCorrectionDict]
```

If `Literal` isn't imported yet, add `from typing import Literal` at the top of `schemas.py`.

- [ ] **Step 2: Add chat_model field** to `tutor/web/deps.py`

Read `deps.py` and find the `Dependencies` dataclass / class. Add an optional `chat_model: str` field defaulting to the same value as `dialog_model` (since they serve a similar conversational purpose). Look at how `dialog_model` / `evaluator_model` are added in current code — follow that pattern. If `Dependencies` is built via a factory, also wire the value through.

- [ ] **Step 3: Write failing test** `tests/web/test_chat.py`:

```python
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import json


def _client(tmp_path, mocker):
    from tutor.web.api import create_app
    from tutor.web.deps import Dependencies
    from tutor.storage import SessionStorage

    deps = Dependencies(
        storage=SessionStorage(root=tmp_path),
        llm=MagicMock(),
        asr=MagicMock(),
        srs=MagicMock(),
        budget=MagicMock(),
        dialog_model="m-dialog",
        evaluator_model="m-eval",
        grader_model="m-grade",
        tts_service=MagicMock(),
        tts_voice="alloy",
        chat_model="m-chat",
    )
    app = create_app(deps=deps)
    return TestClient(app), deps


def test_post_chat_returns_reply_and_corrections(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = json.dumps({
        "reply": "That's interesting!",
        "corrections": [{
            "tag": "grammar",
            "user_utterance": "I readed",
            "corrected_version": "I read",
            "explanation": "Past tense of read is irregular.",
        }],
    })
    r = client.post("/api/chat", json={"history": [], "message": "I readed a book"})
    assert r.status_code == 200
    data = r.json()
    assert data["reply"] == "That's interesting!"
    assert len(data["corrections"]) == 1
    assert data["corrections"][0]["tag"] == "grammar"


def test_post_chat_passes_history_to_llm(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ]
    r = client.post("/api/chat", json={"history": history, "message": "How are you?"})
    assert r.status_code == 200
    # Verify the LLM received history in its messages
    call_kwargs = deps.llm.complete.call_args.kwargs
    msgs = call_kwargs["messages"]
    assert any(m["role"] == "user" and m["content"] == "Hello" for m in msgs)
    assert any(m["role"] == "assistant" and m["content"] == "Hi!" for m in msgs)
    assert msgs[-1] == {"role": "user", "content": "How are you?"}


def test_post_chat_rejects_empty_message(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/chat", json={"history": [], "message": ""})
    assert r.status_code == 422
```

(Adapt `_client` to match the actual `Dependencies` constructor signature found in `tutor/web/deps.py`.)

- [ ] **Step 4: Run** `pytest tests/web/test_chat.py -v` → 3 fail.

- [ ] **Step 5: Add service** in `tutor/web/services.py`:

```python
def chat_service(
    deps: Dependencies,
    history: list[dict[str, str]],
    message: str,
) -> dict:
    """Stateless free-chat turn: returns {reply, corrections} via one LLM call."""
    from tutor.conversation import ChatTurn

    chat = ChatTurn(llm=deps.llm, model=deps.chat_model)
    response = chat.respond(history=history, message=message)
    return response.model_dump()
```

- [ ] **Step 6: Add route** in `tutor/web/api.py`

Add to imports:
```python
from tutor.web.schemas import ChatRequest, ChatResponseDict
```

Add route alongside other POSTs:
```python
    @app.post("/api/chat", response_model=ChatResponseDict)
    async def chat(req: ChatRequest, d: Dependencies = Depends(get_deps)):
        if not req.message.strip():
            raise HTTPException(status_code=422, detail="message is required")
        history = [{"role": m.role, "content": m.content} for m in req.history]
        return services.chat_service(d, history=history, message=req.message)
```

- [ ] **Step 7: Run + commit**

```bash
pytest tests/web/test_chat.py -v
pytest 2>&1 | tail -5
```
→ all green, 183 total.

```bash
git add tutor/web/schemas.py tutor/web/services.py tutor/web/api.py tutor/web/deps.py tests/web/test_chat.py
git commit -m "feat(web): POST /api/chat — free chat with per-message corrections"
```

## Context

- Branch: `main`. Previous: T1 commit.
- Task 2 of 6.

---

## Task 3: Frontend types + API client

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Append types** to `frontend/src/api/types.ts`:

```typescript
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
```

- [ ] **Step 2: Append failing test** in `frontend/src/api/client.test.ts`:

```typescript
it("chat posts history and message, returns reply + corrections", async () => {
  (globalThis as any).fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      reply: "ok",
      corrections: [{ tag: "grammar", user_utterance: "a", corrected_version: "b", explanation: "e" }],
    }),
  });
  const res = await api.chat([{ role: "user", content: "hi" }], "I goed");
  expect(res.reply).toBe("ok");
  expect(res.corrections).toHaveLength(1);
  const call = ((globalThis as any).fetch as any).mock.calls[0];
  expect(call[0]).toBe("/api/chat");
  const body = JSON.parse(call[1].body);
  expect(body.history).toEqual([{ role: "user", content: "hi" }]);
  expect(body.message).toBe("I goed");
});
```

- [ ] **Step 3: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test client` → fail.

- [ ] **Step 4: Add to `api` object** in `client.ts`:

```typescript
  chat(history: ChatMessageDict[], message: string): Promise<ChatResponseDict> {
    return request<ChatResponseDict>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ history, message }),
    });
  },
```

Update imports if needed (add `ChatMessageDict`, `ChatResponseDict`).

- [ ] **Step 5: Run + commit**

```bash
npm test 2>&1 | tail -5
npm run build 2>&1 | tail -5

cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/api/
git commit -m "feat(chat): api.chat(history, message)"
```

## Context

- Branch: `main`. Previous: T2 commit.
- Task 3 of 6.

---

## Task 4: `ChatPage` component with localStorage persistence

**Files:**
- Create: `frontend/src/pages/ChatPage.tsx`
- Create: `frontend/src/pages/ChatPage.test.tsx`

- [ ] **Step 1: Write failing tests** `frontend/src/pages/ChatPage.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders empty state initially", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { chat: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    expect(screen.getByPlaceholderText(/type a message/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start over/i })).toBeInTheDocument();
  });

  it("sends a message and renders reply + correction", async () => {
    vi.resetModules();
    const chatMock = vi.fn().mockResolvedValue({
      reply: "Cool, tell me more!",
      corrections: [{
        tag: "grammar",
        user_utterance: "I readed",
        corrected_version: "I read",
        explanation: "Past tense of read is irregular.",
      }],
    });
    vi.doMock("../api/client", () => ({
      api: { chat: chatMock },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    const input = screen.getByPlaceholderText(/type a message/i);
    fireEvent.change(input, { target: { value: "I readed a book" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));

    await waitFor(() => {
      expect(screen.getByText("I readed a book")).toBeInTheDocument();
      expect(screen.getByText("Cool, tell me more!")).toBeInTheDocument();
      expect(screen.getByText("I read")).toBeInTheDocument();
      expect(screen.getByText("Past tense of read is irregular.")).toBeInTheDocument();
    });
    expect(chatMock).toHaveBeenCalledTimes(1);
  });

  it("persists messages to localStorage", async () => {
    vi.resetModules();
    const chatMock = vi.fn().mockResolvedValue({ reply: "ok", corrections: [] });
    vi.doMock("../api/client", () => ({
      api: { chat: chatMock },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    const input = screen.getByPlaceholderText(/type a message/i);
    fireEvent.change(input, { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: /send/i }));
    await waitFor(() => {
      expect(screen.getByText("ok")).toBeInTheDocument();
    });
    const stored = localStorage.getItem("chat_history");
    expect(stored).not.toBeNull();
    const parsed = JSON.parse(stored!);
    expect(parsed.length).toBeGreaterThan(0);
  });

  it("restores messages from localStorage on mount", async () => {
    localStorage.setItem("chat_history", JSON.stringify([
      { role: "user", content: "prior question", corrections: [] },
      { role: "assistant", content: "prior answer" },
    ]));
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { chat: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    expect(screen.getByText("prior question")).toBeInTheDocument();
    expect(screen.getByText("prior answer")).toBeInTheDocument();
  });

  it("Start over clears state and localStorage", async () => {
    localStorage.setItem("chat_history", JSON.stringify([
      { role: "user", content: "old", corrections: [] },
      { role: "assistant", content: "old reply" },
    ]));
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { chat: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { ChatPage } = await import("./ChatPage");
    render(wrap(<ChatPage />));
    expect(screen.getByText("old")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /start over/i }));
    await waitFor(() => {
      expect(screen.queryByText("old")).not.toBeInTheDocument();
    });
    expect(localStorage.getItem("chat_history")).toBeNull();
  });
});
```

- [ ] **Step 2: Run** `npm test ChatPage` → 5 fail.

- [ ] **Step 3: Implement `frontend/src/pages/ChatPage.tsx`**:

```typescript
import { useState, useEffect, useRef, FormEvent } from "react";
import { api } from "../api/client";
import type { ChatCorrectionDict, ChatMessageDict } from "../api/types";
import { MessageBubble } from "../components/MessageBubble";
import { InlineCorrection } from "../components/InlineCorrection";

const STORAGE_KEY = "chat_history";

interface ChatMessage extends ChatMessageDict {
  corrections?: ChatCorrectionDict[];
}

function loadFromStorage(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
    return [];
  } catch {
    return [];
  }
}

export function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadFromStorage());
  const [input, setInput] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Persist to localStorage on every change
  useEffect(() => {
    if (messages.length === 0) {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    }
  }, [messages]);

  // Auto-scroll to bottom on new message
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function send(e?: FormEvent) {
    e?.preventDefault();
    const text = input.trim();
    if (!text || isSending) return;
    setInput("");
    setIsSending(true);
    setError(null);

    const userMsg: ChatMessage = { role: "user", content: text };
    const newHistory = [...messages, userMsg];
    setMessages(newHistory);

    try {
      // Send the conversation BEFORE the new user message; server reconstructs full prompt.
      const historyForServer: ChatMessageDict[] = messages.map(({ role, content }) => ({ role, content }));
      const res = await api.chat(historyForServer, text);
      setMessages((prev) => {
        const copy = [...prev];
        // Attach corrections to the user message we just appended
        const lastUserIdx = copy.findLastIndex((m) => m.role === "user");
        if (lastUserIdx >= 0) copy[lastUserIdx] = { ...copy[lastUserIdx], corrections: res.corrections };
        copy.push({ role: "assistant", content: res.reply });
        return copy;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setIsSending(false);
    }
  }

  function startOver() {
    setMessages([]);
    setInput("");
    setError(null);
    localStorage.removeItem(STORAGE_KEY);
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)] max-w-3xl mx-auto w-full">
      <div className="px-4 py-3 border-b flex items-center justify-between">
        <h1 className="text-lg font-semibold text-slate-900">Free chat</h1>
        <button
          type="button"
          onClick={startOver}
          className="text-xs text-slate-600 hover:text-slate-900 border border-slate-300 rounded px-3 py-1.5 hover:bg-slate-50"
        >
          Start over
        </button>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 ? (
          <div className="text-center text-slate-500 text-sm pt-8">
            Type a message to start chatting. The bot will reply and suggest corrections for your text.
          </div>
        ) : (
          <div>
            {messages.map((m, i) => (
              <div key={i}>
                <MessageBubble role={m.role} text={m.content} />
                {m.role === "user" && m.corrections && m.corrections.length > 0 && (
                  <div>
                    {m.corrections.map((c, j) => (
                      <InlineCorrection
                        key={j}
                        growth_point={{ ...c, context: null }}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="px-4 py-2 bg-red-50 border-t border-red-200 text-sm text-red-800">
          {error}
        </div>
      )}

      <form onSubmit={send} className="border-t p-3 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type a message..."
          disabled={isSending}
          className="flex-1 border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500 disabled:opacity-60"
          aria-label="Chat input"
        />
        <button
          type="submit"
          disabled={isSending || !input.trim()}
          className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-4 py-2 rounded text-sm font-medium"
        >
          {isSending ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
```

Note: `Array.prototype.findLastIndex` is ES2023. Modern browsers + Vite support it. If TS complains, add `"lib": [..., "ES2023"]` to `tsconfig.json` or use a manual reverse loop.

- [ ] **Step 4: Run + commit**

```bash
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5

cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/pages/ChatPage.tsx frontend/src/pages/ChatPage.test.tsx
git commit -m "feat(chat): ChatPage with text input + inline corrections + localStorage"
```

## Context

- Branch: `main`. Previous: T3 commit.
- Task 4 of 6.

---

## Task 5: Wire `/chat` route + Layout nav

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/components/Layout.test.tsx`

- [ ] **Step 1: Update `App.tsx`**

Add import:
```typescript
import { ChatPage } from "./pages/ChatPage";
```

Add route alongside others:
```typescript
<Route path="/chat" element={<ChatPage />} />
```

Result block:
```typescript
<Routes>
  <Route path="/" element={<ScenariosPage />} />
  <Route path="/session/:id" element={<SessionPage />} />
  <Route path="/review" element={<ReviewPage />} />
  <Route path="/review/:sessionId" element={<ReviewDetail />} />
  <Route path="/practice" element={<PracticePage />} />
  <Route path="/chat" element={<ChatPage />} />
  <Route path="/stats" element={<StatsPage />} />
</Routes>
```

- [ ] **Step 2: Update `Layout.tsx`** — add Chat nav link

Find the nav block. Add between Practice and Stats:
```typescript
<Link to="/chat" className="hover:text-slate-900">Chat</Link>
```

Order in header: Scenarios | Review | Practice | Chat | Stats.

- [ ] **Step 3: Update `Layout.test.tsx`** — add assertion for Chat link

Look at the existing Practice / Stats assertions and follow the same pattern. Add `expect(screen.getByText(/chat/i)).toBeInTheDocument();` (or scope to the nav if needed).

- [ ] **Step 4: Run + commit**

```bash
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5

cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/App.tsx frontend/src/components/Layout.tsx frontend/src/components/Layout.test.tsx
git commit -m "feat(chat): wire /chat route + Chat nav link"
```

## Context

- Branch: `main`. Previous: T4 commit.
- Task 5 of 6.

---

## Task 6: Manual smoke

- [ ] **Step 1: Run all suites + build + push**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest 2>&1 | tail -5
cd frontend && npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5

cd /Users/sarkhipov/Work/Personal/english-tutor
git push origin main
```

Expect pytest ~187 green (180 + 7), npm test ~50 green (42 + 8 = 50), build clean.

- [ ] **Step 2: Run web UI**

`./scripts/build_and_serve.sh` → `http://127.0.0.1:8000`

Checks:

1. Header nav shows: **Scenarios | Review | Practice | Chat | Stats**. Click Chat → `/chat`.
2. Empty state visible: "Type a message to start chatting…" + input field + Start over button.
3. Type "I goed to the store yesterday" → Send. Within 2-3s:
   - Your message appears in a user bubble.
   - Below it: an InlineCorrection card showing "I goed" → "I went" with explanation.
   - Then an assistant bubble with the bot's reply.
4. Continue typing 2-3 more messages. Each user message gets its own corrections (or no corrections if clean).
5. Refresh the page (Cmd+R). Chat history should persist — same messages still visible.
6. Click "Start over". Conversation clears. Empty state again.
7. Clear browser cache/cookies → reload → empty again (localStorage was tied to the site origin).

- [ ] **Step 3: Report findings**

If anything regresses or behaves unexpectedly, file follow-up. Otherwise Stage 2d done.

## Context

- Branch: `main`. Previous: T5 commit.
- Task 6 of 6.

---

## Self-review

1. **Spec coverage:**
   - Free chat with topic-free conversation → T1 + T2 ✓
   - Per-message corrections inline → T1 (prompt) + T4 (render) ✓
   - "Start over" button clears context → T4 ✓
   - Survives tab reload via localStorage → T4 ✓
   - Dies on cache clear (localStorage wipe) → T4 (no backend persistence) ✓
   - New menu item → T5 ✓
   - No SRS card creation → T2 service doesn't call SRS ✓

2. **Type consistency:**
   - `ChatCorrectionDict` and `GrowthPointDict` share `tag/user_utterance/corrected_version/explanation` fields. `InlineCorrection` component takes `GrowthPointDict`. ChatPage maps via `{ ...c, context: null }` to inject the missing `context` field. Works because `GrowthPointDict.context` is `string | null`.
   - Backend `ChatMessage`, `ChatCorrectionDict`, `ChatResponseDict` shapes mirror the frontend.

3. **No placeholders:** all code shown. The `Dependencies` constructor wiring in deps.py is the only "look at existing pattern" step — straightforward field addition.

4. **Failure modes:**
   - LLM returns invalid JSON twice → ChatResponse returns fallback reply, no corrections → T1 tests cover.
   - Network error on frontend → red error bar shown → T4 handles via try/catch (test not added for brevity but path covered).
   - Empty message → 422 → T2 test.

---

## Definition of Done

- 5 task commits + manual smoke on `origin/main`.
- pytest ~187 green.
- npm test ~50 green.
- npm run build succeeds.
- `/chat` works: send → bubble + corrections + reply.
- Chat persists across reload, cleared by "Start over" or browser cache wipe.
- No regressions in existing pages.
