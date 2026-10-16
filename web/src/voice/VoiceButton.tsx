import { MicIcon } from "../components/icons";
import { IconButton } from "../components/ui";
import "./voice.css";

/** The mic button in the search bar. Rendered only when the browser supports speech recognition. */
export function VoiceButton({ listening, onStart, onStop, disabled }: { listening: boolean; onStart: () => void; onStop: () => void; disabled?: boolean }) {
  return (
    <IconButton
      label={listening ? "Stop listening" : "Search by voice"}
      aria-pressed={listening}
      className={`sf-voice ${listening ? "is-listening" : ""}`}
      disabled={disabled}
      onClick={listening ? onStop : onStart}
    >
      <MicIcon />
    </IconButton>
  );
}
