import { useCallback, useState } from "react";
import { api, ApiError } from "../api/client";
import { OPENAI_TTS_VOICES } from "../api/types";

export interface UseTTS {
  speak: (text: string) => Promise<void>;
  isSpeaking: boolean;
  voices: readonly string[];
  lastError: string | null;
}

function findBrowserVoice(picked: string | undefined): SpeechSynthesisVoice | null {
  if (!picked || typeof speechSynthesis === "undefined") return null;
  const all = speechSynthesis.getVoices();
  const target = picked.toLowerCase();
  return (
    all.find((v) => v.name.toLowerCase().includes(target)) ||
    all.find((v) => v.name.toLowerCase().includes("english")) ||
    null
  );
}

async function speakWithBrowser(text: string, picked: string | undefined): Promise<void> {
  if (typeof speechSynthesis === "undefined") return;
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    const voice = findBrowserVoice(picked);
    if (voice) u.voice = voice;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}

export function useTTS(): UseTTS {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

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
      setLastError(null);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? (e.body?.message as string) || (e.body?.error as string) || `HTTP ${e.status}`
          : e instanceof Error
          ? e.message
          : "TTS failed";
      setLastError(msg);
      await speakWithBrowser(text, voice);
    } finally {
      setIsSpeaking(false);
    }
  }, []);

  return { speak, isSpeaking, voices: OPENAI_TTS_VOICES, lastError };
}
