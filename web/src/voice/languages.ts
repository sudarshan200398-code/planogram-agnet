/**
 * Languages for voice search, tried in order. Hindi and Tamil are listed so they can be switched on
 * later by setting `enabled: true` (and checking the parser handles them); they are not shipped now.
 */
export interface VoiceLanguage {
  code: string;
  label: string;
  enabled: boolean;
}

export const VOICE_LANGUAGES: readonly VoiceLanguage[] = [
  { code: "en-IN", label: "English (India)", enabled: true },
  { code: "en-US", label: "English (US)", enabled: true },
  { code: "hi-IN", label: "हिन्दी", enabled: false },
  { code: "ta-IN", label: "தமிழ்", enabled: false },
];

export const activeVoiceLanguages = () => VOICE_LANGUAGES.filter((l) => l.enabled);
