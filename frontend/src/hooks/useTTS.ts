import { useCallback, useState } from "react";
import { api } from "../api/client";
import { OPENAI_TTS_VOICES } from "../api/types";

export interface UseTTS {
  speak: (text: string) => Promise<void>;
  isSpeaking: boolean;
  voices: readonly string[];
}

async function speakWithBrowser(text: string): Promise<void> {
  if (typeof speechSynthesis === "undefined") return;
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.onend = () => resolve();
    u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}

export function useTTS(): UseTTS {
  const [isSpeaking, setIsSpeaking] = useState(false);

  const speak = useCallback(async (text: string): Promise<void> => {
    if (!text.trim()) return;
    const voice = localStorage.getItem("ttsVoice") || undefined;
    setIsSpeaking(true);
    try {
      const blob = await api.synthesizeTTS(text, voice);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
        audio.onerror = () => { URL.revokeObjectURL(url); reject(); };
        audio.play().catch(reject);
      });
    } catch {
      // Backend TTS failed — fallback to browser SpeechSynthesis
      await speakWithBrowser(text);
    } finally {
      setIsSpeaking(false);
    }
  }, []);

  return { speak, isSpeaking, voices: OPENAI_TTS_VOICES };
}
