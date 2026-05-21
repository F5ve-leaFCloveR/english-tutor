import type { Card } from "../api/types";
import { PushToTalkButton } from "./PushToTalkButton";

interface Props {
  card: Card;
  isRecording: boolean;
  isBusy: boolean;
  onStart: () => void;
  onStop: () => void;
  onSkip: () => void;
  onQuit: () => void;
}

export function ReviewCard({ card, isRecording, isBusy, onStart, onStop, onSkip, onQuit }: Props) {
  return (
    <div className="max-w-2xl mx-auto p-6 w-full">
      <div className="bg-white border border-slate-200 rounded-lg p-6 mb-6 shadow-sm">
        <div className="text-xs uppercase text-slate-500 mb-3">{card.tag}</div>
        {card.context && (
          <div className="text-sm text-slate-600 mb-3">Context: {card.context}</div>
        )}
        <div className="text-base text-slate-900 mb-2">Earlier you said:</div>
        <div className="text-lg italic text-slate-700">"{card.user_utterance}"</div>
      </div>
      <p className="text-center text-slate-700 mb-6">How would you say it more precisely?</p>
      <div className="flex items-center justify-center gap-6">
        <PushToTalkButton
          onStart={onStart}
          onStop={onStop}
          isRecording={isRecording}
          isBusy={isBusy}
        />
        <div className="flex flex-col gap-2 text-sm">
          <button
            onClick={onSkip}
            disabled={isBusy}
            className="px-4 py-2 text-slate-600 hover:text-slate-900 disabled:opacity-50"
          >
            Skip
          </button>
          <button
            onClick={onQuit}
            disabled={isBusy}
            className="px-4 py-2 text-slate-600 hover:text-slate-900 disabled:opacity-50"
          >
            Quit
          </button>
        </div>
      </div>
    </div>
  );
}
