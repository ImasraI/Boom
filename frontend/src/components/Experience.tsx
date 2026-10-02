import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";

export type SoundKind = "tap" | "success";
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
/** Synthesized locally; no audio downloads, tracking, or autoplay. */
export function playFeedback(kind: SoundKind = "tap") {
  if (!readPreferences().sound) return;
  if (kind === "tap" && Date.now() - lastTap < 65) return;
  lastTap = Date.now();
  try {
    audio ??= new AudioContext();
    if (audio.state === "suspended") void audio.resume().catch(() => {});
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
  // invisible effects: palette/calm data-attributes, tap sounds, click rings
  // and success toasts.
  const [prefs, setPrefs] = useState(readPreferences);
  useEffect(() => {
    const sync = () => setPrefs(readPreferences());
    window.addEventListener(PREFERENCES_CHANGED_EVENT, sync);
    return () => window.removeEventListener(PREFERENCES_CHANGED_EVENT, sync);
  }, []);
  const [toast, setToast] = useState<{ text: string; id: number } | null>(null);
  const [rings, setRings] = useState<{ x: number; y: number; id: number }[]>([]);
  const timers = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const sequence = useRef(0);
  useEffect(() => {
    document.documentElement.dataset.palette = prefs.palette;
    document.documentElement.dataset.calm = String(prefs.calm);
  }, [prefs]);
  useEffect(() => {
    const reduced = () => readPreferences().calm || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const click = (event: MouseEvent) => {
      const button = event.target instanceof Element ? event.target.closest("button") : null;
      if (!button || button.disabled || button.getAttribute("aria-disabled") === "true") return;
      if (!button.hasAttribute("data-silent")) playFeedback();
      if (reduced() || event.detail === 0) return;
      const id = ++sequence.current;
      setRings(old => [...old.slice(-3), {x: event.clientX, y: event.clientY, id}]);
      const timer = setTimeout(() => { setRings(old => old.filter(r => r.id !== id)); timers.current.delete(timer); }, 480);
      timers.current.add(timer);
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
    window.addEventListener("boom-celebrate", success);
    return () => {
      document.removeEventListener("click", click, true);
      window.removeEventListener("boom-celebrate", success);
      timers.current.forEach(clearTimeout); timers.current.clear();
      clearTimeout(toastTimer.current);
    };
  }, []);
  return <>
    <div className="feedback-layer" aria-hidden="true">{rings.map(r => <span className="click-ring" key={r.id} style={{left:r.x,top:r.y}} />)}</div>
    <div className="feedback-announcement" role="status" aria-live="polite" aria-atomic="true">{toast && <div key={toast.id} className="success-toast"><span className="success-seal">✓</span><div><strong>یک قدم جلوتر!</strong><p>{toast.text}</p></div><button aria-label="بستن پیام" onClick={() => setToast(null)}>×</button><div className="success-sparks" aria-hidden="true">{Array.from({length:8},(_,i) => <i key={i} style={{"--i":i} as CSSProperties} />)}</div></div>}</div>
  </>;
}
