import { useEffect, useRef, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import { MessageBubble } from "../components/MessageBubble";
import { PushToTalkButton } from "../components/PushToTalkButton";
import { useRecorder } from "../hooks/useRecorder";
import { useTTS } from "../hooks/useTTS";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [errorToast, setErrorToast] = useState<string | null>(null);

  const recorder = useRecorder();
  const tts = useTTS();

  const playedOpeningRef = useRef(false);

  useEffect(() => {
    if (playedOpeningRef.current) return;
    const opening = messages.find((m) => m.role === "assistant")?.text;
    if (opening) {
      playedOpeningRef.current = true;
      tts.speak(opening).catch(() => { /* non-fatal */ });
    }
  }, [messages, tts]);

  // Load session on mount; if route state has opening, seed initial messages quickly
  const initialOpening = (location.state as { opening?: string } | null)?.opening;
  useQuery({
    queryKey: ["session", id],
    queryFn: async () => {
      const data = await api.getSession(id!);
      const msgs: ChatMessage[] = [];
      if (data.opening_text) msgs.push({ role: "assistant", text: data.opening_text });
      for (const t of data.turns) {
        msgs.push({ role: "user", text: t.user_text });
        msgs.push({ role: "assistant", text: t.llm_text });
      }
      setMessages(msgs);
      return data;
    },
    enabled: !!id,
  });

  // If we navigated here with opening text in state, seed immediately for snappier UI
  useEffect(() => {
    if (initialOpening && messages.length === 0) {
      setMessages([{ role: "assistant", text: initialOpening }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const turnMutation = useMutation({
    mutationFn: async (audio: Blob) => api.submitTurn(id!, audio),
    onSuccess: async (result) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", text: result.user_text },
        { role: "assistant", text: result.assistant_text },
      ]);
      try {
        await tts.speak(result.assistant_text);
      } catch {
        /* TTS failure non-fatal */
      }
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.body.error === "no_speech_detected") {
          setErrorToast("Didn't catch that — try again");
        } else if (err.body.error === "budget_exhausted") {
          setErrorToast(`Budget cap reached. Resets at midnight.`);
        } else {
          setErrorToast(err.message);
        }
      } else {
        setErrorToast((err as Error).message);
      }
      setTimeout(() => setErrorToast(null), 4000);
    },
  });

  const endMutation = useMutation({
    mutationFn: () => api.endSession(id!),
    onSuccess: () => {
      navigate("/");
    },
  });

  const handleStart = async () => {
    setErrorToast(null);
    try {
      await recorder.startRecording();
    } catch {
      setErrorToast("Mic permission required");
    }
  };

  const handleStop = async () => {
    const blob = await recorder.stopRecording();
    if (!blob) return;
    turnMutation.mutate(blob);
  };

  const isBusy = turnMutation.isPending || endMutation.isPending;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex-1 overflow-y-auto p-4 max-w-3xl mx-auto w-full">
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            role={m.role}
            text={m.text}
            isSpeaking={m.role === "assistant" && tts.isSpeaking && i === messages.length - 1}
          />
        ))}
      </div>
      <div className="border-t bg-white px-4 py-4 flex items-center justify-center gap-6">
        <PushToTalkButton
          onStart={handleStart}
          onStop={handleStop}
          isRecording={recorder.isRecording}
          isBusy={isBusy}
        />
        <button
          onClick={() => endMutation.mutate()}
          disabled={isBusy}
          className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900 disabled:opacity-50"
        >
          End session
        </button>
      </div>
      {errorToast && (
        <div className="fixed bottom-32 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-sm px-4 py-2 rounded shadow-lg">
          {errorToast}
        </div>
      )}
    </div>
  );
}
