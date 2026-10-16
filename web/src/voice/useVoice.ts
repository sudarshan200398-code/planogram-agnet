import { useCallback, useEffect, useRef, useState } from "react";
import { activeVoiceLanguages } from "./languages";

/** The small part of the Web Speech API we use (not in TypeScript's DOM types). */
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

function recognitionCtor(): RecognitionCtor | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export type VoiceStatus = "idle" | "listening" | "heard" | "error";

const MESSAGES: Record<string, string> = {
  "not-allowed": "Microphone access is off. Allow it in your browser settings, or type instead.",
  "service-not-allowed": "Microphone access is off. Allow it in your browser settings, or type instead.",
  "no-speech": "We didn't hear anything. Try again.",
  "audio-capture": "We couldn't find a microphone. You can type instead.",
  network: "Voice search needs a connection. You can type instead.",
  unsupported: "Voice search isn't available in this browser. You can type instead.",
};

/**
 * Voice search with the browser's speech recognition. The transcript is handed to `onTranscript` as it
 * arrives; the caller puts it in the search bar for the shopper to check. Nothing is searched here.
 */
export function useVoice(onTranscript: (text: string) => void) {
  const [supported] = useState(() => recognitionCtor() !== null);
  const [status, setStatus] = useState<VoiceStatus>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const rec = useRef<Recognition | null>(null);
  const heard = useRef(false);
  const transcriptCb = useRef(onTranscript);
  transcriptCb.current = onTranscript;

  const listen = useCallback((langIndex: number) => {
    const Ctor = recognitionCtor();
    const lang = activeVoiceLanguages()[langIndex];
    if (!Ctor || !lang) {
      setStatus("error");
      setMessage(MESSAGES.unsupported!);
      return;
    }
    const r = new Ctor();
    rec.current = r;
    r.lang = lang.code;
    r.interimResults = true;
    r.continuous = false;
    r.maxAlternatives = 1;
    let failed = false;
    r.onresult = (e) => {
      const text = Array.from(e.results, (res) => res[0]?.transcript ?? "").join(" ").replace(/\s+/g, " ").trim();
      if (text) {
        heard.current = true;
        transcriptCb.current(text);
      }
    };
    r.onerror = (e) => {
      if (rec.current !== r) return;
      failed = true;
      if (e.error === "language-not-supported") {
        rec.current = null;
        listen(langIndex + 1); // next language in the list, once each
        return;
      }
      if (e.error === "aborted") return;
      setStatus("error");
      setMessage(MESSAGES[e.error] ?? "Voice search stopped. Try again, or type instead.");
    };
    r.onend = () => {
      if (rec.current !== r) return;
      rec.current = null;
      if (failed) return;
      if (heard.current) {
        setStatus("heard");
        setMessage("Check the words, then tap Search.");
      } else {
        setStatus("idle");
        setMessage(null);
      }
    };
    setStatus("listening");
    setMessage("Listening…");
    r.start();
  }, []);

  const start = useCallback(() => {
    heard.current = false;
    listen(0);
  }, [listen]);

  const stop = useCallback(() => rec.current?.stop(), []);

  useEffect(() => () => rec.current?.abort(), []);

  return { supported, listening: status === "listening", status, message, start, stop };
}
