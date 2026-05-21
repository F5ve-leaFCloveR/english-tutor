import { Mic } from "lucide-react";

interface Props {
  onStart: () => void;
  onStop: () => void;
  isRecording: boolean;
  isBusy: boolean;
}

export function PushToTalkButton({ onStart, onStop, isRecording, isBusy }: Props) {
  const handleDown = (e: React.PointerEvent) => {
    e.preventDefault();
    if (!isBusy) onStart();
  };
  const handleUp = (e: React.PointerEvent) => {
    e.preventDefault();
    onStop();
  };

  return (
    <button
      type="button"
      onPointerDown={handleDown}
      onPointerUp={handleUp}
      onPointerLeave={handleUp}
      disabled={isBusy}
      aria-label="Press and hold to speak"
      className={
        `w-24 h-24 rounded-full flex flex-col items-center justify-center select-none ` +
        `text-white shadow-lg transition-transform ` +
        (isRecording
          ? "bg-red-600 animate-pulse scale-110"
          : isBusy
          ? "bg-slate-400 cursor-not-allowed"
          : "bg-blue-600 hover:bg-blue-700 active:scale-95")
      }
    >
      <Mic className="w-8 h-8" />
      <span className="text-xs mt-1">
        {isBusy ? "Working…" : isRecording ? "Release" : "Speak"}
      </span>
    </button>
  );
}
