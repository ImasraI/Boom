import { useEffect, useRef, useState } from "react";
import { CheckMark } from "./icons";

export type SoundKind = "tap" | "success" | "type";
const KEY = "boom-experience";
/** Fired (window CustomEvent) whenever preferences change, so every surface
 * showing the same controls (e.g. the Profile settings tab) stays in sync. */
export const PREFERENCES_CHANGED_EVENT = "boom-experience-changed";
type Preferences = { sound: boolean; calm: boolean; palette: "coral" | "mint" | "iris" };
const defaults: Preferences = { sound: false, calm: false, palette: "coral" };
export function readPreferences(): Preferences {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) || "{}");
    return { sound: value.sound === true, calm: value.calm === true,
      palette: ["coral", "mint", "iris"].includes(value.palette) ? value.palette : "coral" };
  } catch { return defaults; }
}
let audio: AudioContext | undefined;
let lastTap = 0;
let lastType = 0;
let typingNoise: AudioBuffer | undefined;
/** Synthesized locally; no audio downloads, tracking, or autoplay. */
export function playFeedback(kind: SoundKind = "tap") {
  if (!readPreferences().sound) return;
  if (kind === "tap" && Date.now() - lastTap < 65) return;
  if (kind === "type" && Date.now() - lastType < 28) return;
  if (kind === "type") lastType = Date.now(); else lastTap = Date.now();
  try {
    audio ??= new AudioContext();
    if (audio.state === "suspended") void audio.resume().catch(() => {});
    if (kind === "type") {
      // The_Goal's soft mechanical keystroke recipe, including its master volume.
      const t = audio.currentTime;
      const master = audio.createGain(); master.gain.value = 0.55; master.connect(audio.destination);
      const osc = audio.createOscillator(); const body = audio.createGain();
      osc.frequency.setValueAtTime(430, t); osc.frequency.exponentialRampToValueAtTime(260, t + 0.03);
      body.gain.setValueAtTime(0.0001, t); body.gain.exponentialRampToValueAtTime(0.13, t + 0.006);
      body.gain.exponentialRampToValueAtTime(0.0001, t + 0.03);
      osc.connect(body); body.connect(master); osc.start(t); osc.stop(t + 0.06);
      if (!typingNoise) {
        typingNoise = audio.createBuffer(1, Math.floor(audio.sampleRate * 0.12), audio.sampleRate);
        const samples = typingNoise.getChannelData(0);
        for (let i = 0; i < samples.length; i++) samples[i] = Math.random() * 2 - 1;
      }
      const noise = audio.createBufferSource(); noise.buffer = typingNoise; noise.playbackRate.value = 0.9 + Math.random() * 0.2;
      const filter = audio.createBiquadFilter(); filter.type = "bandpass"; filter.frequency.value = 3000; filter.Q.value = 1.6;
      const tick = audio.createGain(); tick.gain.setValueAtTime(0.1, t); tick.gain.exponentialRampToValueAtTime(0.0001, t + 0.007);
      noise.connect(filter); filter.connect(tick); tick.connect(master); noise.start(t, Math.random() * 0.05); noise.stop(t + 0.027);
      noise.onended = () => { noise.disconnect(); filter.disconnect(); tick.disconnect(); };
      osc.onended = () => { osc.disconnect(); body.disconnect(); master.disconnect(); };
      return;
    }
    const notes = kind === "success" ? [523.25, 659.25, 783.99] : [620];
    notes.forEach((frequency, i) => {
      const start = audio!.currentTime + i * 0.075;
      const oscillator = audio!.createOscillator();
      const gain = audio!.createGain();
      oscillator.type = "sine";
      oscillator.frequency.setValueAtTime(frequency, start);
      oscillator.frequency.exponentialRampToValueAtTime(frequency * 0.8, start + 0.12);
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(kind === "success" ? 0.045 : 0.025, start + 0.009);
      gain.gain.exponentialRampToValueAtTime(0.001, start + 0.15);
      oscillator.connect(gain); gain.connect(audio!.destination);
      oscillator.start(start); oscillator.stop(start + 0.17);
      oscillator.onended = () => { oscillator.disconnect(); gain.disconnect(); };
    });
  } catch { /* Browsers without Web Audio retain all visual feedback. */ }
}
export function celebrate(message: string) {
  window.dispatchEvent(new CustomEvent("boom-celebrate", { detail: message }));
}
function SoundIcon({ muted }: { muted: boolean }) {
  return <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M11 5 6 9H3v6h3l5 4z" />{muted ? <path d="m16 9 5 6m0-6-5 6" /> : <><path d="M15 8a6 6 0 0 1 0 8M18 5a10 10 0 0 1 0 14" /></>}</svg>;
}

/** Read-modify-write helper for surfaces that expose a preference control
 * outside this component (the Profile settings tab). */
export function updatePreferences(patch: Partial<Preferences>): Preferences {
  const next = { ...readPreferences(), ...patch };
  try { localStorage.setItem(KEY, JSON.stringify(next)); } catch { /* private browsing */ }
  window.dispatchEvent(new CustomEvent(PREFERENCES_CHANGED_EVENT));
  return next;
}
export { SoundIcon };

export default function Experience() {
  // The floating bar UI was removed — theme/sound/palette controls live in
  // the Profile settings tab now. This component stays mounted only for the
  // invisible effects: palette/calm data-attributes, tap sounds
  // and success toasts.
  const [prefs, setPrefs] = useState(readPreferences);
  useEffect(() => {
    const sync = () => setPrefs(readPreferences());
    window.addEventListener(PREFERENCES_CHANGED_EVENT, sync);
    return () => window.removeEventListener(PREFERENCES_CHANGED_EVENT, sync);
  }, []);
  const [toast, setToast] = useState<{ text: string; id: number } | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const sequence = useRef(0);
  useEffect(() => {
    document.documentElement.dataset.palette = prefs.palette;
    document.documentElement.dataset.calm = String(prefs.calm);
  }, [prefs]);
  useEffect(() => {
    const click = (event: MouseEvent) => {
      const button = event.target instanceof Element ? event.target.closest("button") : null;
      if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") return;
      if (!button.hasAttribute("data-silent")) playFeedback();
    };
    const typing = (event: KeyboardEvent) => {
      if (event.ctrlKey || event.metaKey || event.altKey || event.isComposing || !(event.target instanceof HTMLElement)) return;
      const field = event.target.closest("input, textarea, [contenteditable='true']");
      if (!field || field.hasAttribute("disabled") || field.hasAttribute("readonly")) return;
      if (event.key.length !== 1 && !["Backspace", "Delete", "Enter"].includes(event.key)) return;
      playFeedback("type");
    };
    const success = (event: Event) => {
      const text = (event as CustomEvent<string>).detail;
      if (typeof text !== "string") return;
      playFeedback("success");
      setToast({ text, id: ++sequence.current });
      clearTimeout(toastTimer.current);
      toastTimer.current = setTimeout(() => setToast(null), 3400);
    };
    document.addEventListener("click", click, true);
    document.addEventListener("keydown", typing);
    window.addEventListener("boom-celebrate", success);
    return () => {
      document.removeEventListener("click", click, true);
      document.removeEventListener("keydown", typing);
      window.removeEventListener("boom-celebrate", success);
      clearTimeout(toastTimer.current);
    };
  }, []);
  return <>
    <div className="feedback-announcement" role="status" aria-live="polite" aria-atomic="true">{toast && <div key={toast.id} className="success-toast"><span className="success-seal"><CheckMark size={20} strokeWidth={3} /></span><div><strong>یک قدم جلوتر!</strong><p>{toast.text}</p></div><button aria-label="بستن پیام" onClick={() => setToast(null)}>×</button></div>}</div>
  </>;
}
