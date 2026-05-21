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

  // Auto-scroll to bottom on new message (guard for jsdom where scrollTo is missing)
  useEffect(() => {
    const el = scrollRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
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
        // Attach corrections to the last user message
        for (let i = copy.length - 1; i >= 0; i--) {
          if (copy[i].role === "user") {
            copy[i] = { ...copy[i], corrections: res.corrections };
            break;
          }
        }
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
