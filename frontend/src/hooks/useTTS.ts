import { useCallback, useEffect, useState } from "react";

export interface UseTTS {
  speak: (text: string) => Promise<void>;
  isSpeaking: boolean;
  voices: SpeechSynthesisVoice[];
}

export function useTTS(): UseTTS {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);

  useEffect(() => {
    if (typeof speechSynthesis === "undefined") return;
    const update = () => setVoices(speechSynthesis.getVoices());
    update();
    speechSynthesis.addEventListener?.("voiceschanged", update);
    return () => {
      speechSynthesis.removeEventListener?.("voiceschanged", update);
    };
  }, []);

  const speak = useCallback(
    async (text: string): Promise<void> => {
      if (!text.trim() || typeof speechSynthesis === "undefined") return;
      return new Promise((resolve, reject) => {
        const utter = new SpeechSynthesisUtterance(text);
        const savedVoice = localStorage.getItem("ttsVoice");
        if (savedVoice) {
          const v = voices.find((v) => v.name === savedVoice);
          if (v) utter.voice = v;
        }
        utter.rate = 1.0;
        utter.onend = () => {
          setIsSpeaking(false);
          resolve();
        };
        utter.onerror = (e) => {
          setIsSpeaking(false);
          reject(e);
        };
        setIsSpeaking(true);
        speechSynthesis.speak(utter);
      });
    },
    [voices],
  );

  return { speak, isSpeaking, voices };
}
