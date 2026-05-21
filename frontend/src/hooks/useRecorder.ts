import { useCallback, useRef, useState } from "react";

const MAX_DURATION_MS = 60_000;
const MIN_DURATION_MS = 500;

const MIME_PRIORITY = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/wav",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const m of MIME_PRIORITY) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return undefined;
}

export interface UseRecorder {
  isRecording: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob | null>;
  cancelRecording: () => void;
}

export function useRecorder(): UseRecorder {
  const [isRecording, setIsRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number>(0);
  const cancelledRef = useRef(false);
  const maxTimerRef = useRef<number | null>(null);

  const startRecording = useCallback(async () => {
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    }
    chunksRef.current = [];
    cancelledRef.current = false;

    const mimeType = pickMimeType();
    const rec = new MediaRecorder(
      streamRef.current,
      mimeType ? { mimeType } : undefined,
    );
    recorderRef.current = rec;

    rec.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };

    rec.start();
    startedAtRef.current = performance.now();
    setIsRecording(true);

    // hard cap
    maxTimerRef.current = window.setTimeout(() => {
      if (rec.state === "recording") rec.stop();
    }, MAX_DURATION_MS);
  }, []);

  const stopRecording = useCallback(async (): Promise<Blob | null> => {
    const rec = recorderRef.current;
    if (!rec || rec.state === "inactive") {
      setIsRecording(false);
      return null;
    }
    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    const duration = performance.now() - startedAtRef.current;
    const blob: Blob | null = await new Promise((resolve) => {
      rec.onstop = () => {
        if (cancelledRef.current) {
          resolve(null);
          return;
        }
        if (duration < MIN_DURATION_MS) {
          resolve(null);
          return;
        }
        const mimeType = rec.mimeType || "audio/webm";
        resolve(new Blob(chunksRef.current, { type: mimeType }));
      };
      rec.stop();
    });
    setIsRecording(false);
    return blob;
  }, []);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    const rec = recorderRef.current;
    if (rec && rec.state === "recording") rec.stop();
    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    setIsRecording(false);
  }, []);

  return { isRecording, startRecording, stopRecording, cancelRecording };
}
