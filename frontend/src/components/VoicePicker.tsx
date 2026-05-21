import { useState } from "react";
import { useTTS } from "../hooks/useTTS";

const TEST_SAMPLE = "This is a sample of the selected voice.";

export function VoicePicker() {
  const tts = useTTS();
  const [selected, setSelected] = useState<string>(
    () => localStorage.getItem("ttsVoice") || "alloy"
  );

  const change = (voice: string) => {
    localStorage.setItem("ttsVoice", voice);
    setSelected(voice);
  };

  return (
    <div className="flex items-center gap-2">
      <select
        value={selected}
        onChange={(e) => change(e.target.value)}
        className="text-xs border border-slate-300 rounded px-2 py-1 bg-white text-slate-800"
        aria-label="Choose TTS voice"
      >
        {tts.voices.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => tts.speak(TEST_SAMPLE)}
        disabled={tts.isSpeaking}
        className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-100 disabled:opacity-50"
      >
        Test
      </button>
    </div>
  );
}
