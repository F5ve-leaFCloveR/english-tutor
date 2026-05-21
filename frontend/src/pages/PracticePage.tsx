import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Card, GradeResult } from "../api/types";
import { ReviewCard } from "../components/ReviewCard";
import { useRecorder } from "../hooks/useRecorder";
import { useTTS } from "../hooks/useTTS";

export function PracticePage() {
  const navigate = useNavigate();
  const recorder = useRecorder();
  const tts = useTTS();
  const [index, setIndex] = useState(0);
  const [lastResult, setLastResult] = useState<GradeResult | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["due-cards"],
    queryFn: () => api.getDueCards({}),
  });
  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: () => api.getStats(),
    staleTime: 60_000,
  });

  const gradeMutation = useMutation({
    mutationFn: async (args: { card_id: string; audio: Blob | null; skip: boolean }) =>
      api.gradeCard(args.card_id, args.audio, args.skip),
    onSuccess: async (result) => {
      setLastResult(result);
      try {
        await tts.speak(result.target);
      } catch {
        /* non-fatal */
      }
    },
  });

  if (isLoading) return <div className="p-8 text-slate-600">Loading…</div>;

  const cards = data?.cards ?? [];
  if (cards.length === 0) {
    const cardsTotal = stats?.cards_total ?? 0;
    const hasCards = cardsTotal > 0;
    return (
      <div className="p-8 text-center max-w-md mx-auto">
        <p className="text-slate-700 mb-2 font-medium">
          {hasCards ? "No cards due today." : "No cards yet."}
        </p>
        <p className="text-sm text-slate-500 mb-6">
          {hasCards
            ? `All ${cardsTotal} card${cardsTotal === 1 ? "" : "s"} are scheduled for later. New cards review +1 day after creation — sleep helps long-term memory.`
            : "Practice cards are created automatically from your session corrections. Run your first session to get started — cards become reviewable the next day."}
        </p>
        <button onClick={() => navigate("/")} className="text-blue-600 hover:underline">
          {hasCards ? "Back home" : "Run a session"}
        </button>
      </div>
    );
  }
  if (index >= cards.length) {
    return (
      <div className="p-8 text-center">
        <p className="text-slate-700 mb-4">Done! {cards.length} cards reviewed.</p>
        <button onClick={() => navigate("/")} className="text-blue-600 hover:underline">
          Back home
        </button>
      </div>
    );
  }
  const card: Card = cards[index];

  const advance = () => {
    setLastResult(null);
    setIndex((i) => i + 1);
  };

  const handleStart = async () => {
    try {
      await recorder.startRecording();
    } catch {
      /* mic denial — handled by toast in real impl */
    }
  };
  const handleStop = async () => {
    const blob = await recorder.stopRecording();
    if (!blob) return;
    gradeMutation.mutate({ card_id: card.id, audio: blob, skip: false });
  };
  const handleSkip = () => {
    gradeMutation.mutate({ card_id: card.id, audio: null, skip: true });
  };
  const handleQuit = () => navigate("/");

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="p-4 text-sm text-slate-600 text-center border-b">
        Card {index + 1} / {cards.length}
      </div>
      {lastResult ? (
        <div className="max-w-2xl mx-auto p-6 w-full text-center">
          <div className="text-4xl font-bold mb-3 text-slate-900">{lastResult.quality}/5</div>
          <div className="text-sm text-slate-600 mb-2">You said:</div>
          <div className="italic text-slate-700 mb-4">"{lastResult.user_attempt_text}"</div>
          <div className="text-sm text-slate-600 mb-2">Target:</div>
          <div className="text-lg font-medium text-slate-900 mb-4">"{lastResult.target}"</div>
          <div className="text-sm text-slate-600 mb-6">{lastResult.explanation}</div>
          <button
            onClick={advance}
            className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded"
          >
            Next card
          </button>
        </div>
      ) : (
        <ReviewCard
          card={card}
          isRecording={recorder.isRecording}
          isBusy={gradeMutation.isPending}
          onStart={handleStart}
          onStop={handleStop}
          onSkip={handleSkip}
          onQuit={handleQuit}
        />
      )}
    </div>
  );
}
