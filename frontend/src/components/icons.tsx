import type { ReactNode, SVGProps } from "react";

/**
 * Inline SVG marks for the whole UI.
 *
 * The screens used to draw their check/cross marks, feature icons, trend and
 * repeat arrows and the pipeline-map legend swatch with text glyphs, which
 * render as emoji boxes on some platforms and as unpredictable font shapes on
 * others. These components keep the same look with `currentColor`, so a caller
 * can colour them from the surrounding class (`text-green-600`, inline style)
 * exactly like the glyph each one replaced.
 */

interface MarkProps extends SVGProps<SVGSVGElement> {
  /** Rendered width/height in px; every mark is square. */
  size?: number;
  /** Stroke width in the 24×24 viewBox. */
  strokeWidth?: number;
}

function Mark({ size = 12, strokeWidth = 2.6, children, ...rest }: MarkProps & { children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" focusable="false" {...rest}>
      {children}
    </svg>
  );
}

/** Answer was right (replaces the tick mark). */
export function CheckMark(props: MarkProps) {
  return <Mark {...props}><path d="M4 12.5 9.5 18 20 6" /></Mark>;
}

/** Answer was wrong (replaces the cross mark). */
export function CrossMark(props: MarkProps) {
  return <Mark {...props}><path d="M6 6l12 12M18 6 6 18" /></Mark>;
}

/** Dismiss / delete control (replaces the heavy multiplication cross). */
export function CloseIcon(props: MarkProps) {
  return <Mark strokeWidth={2.2} {...props}><path d="M6 6l12 12M18 6 6 18" /></Mark>;
}

/** Improvement / promotion direction (replaces the up arrow glyph). */
export function TrendUpIcon(props: MarkProps) {
  return <Mark {...props}><path d="M12 20V5M6 11l6-6 6 6" /></Mark>;
}

/** Recurring block in the weekly schedule (replaces the clockwise arrow). */
export function RepeatIcon(props: MarkProps) {
  return (
    <Mark strokeWidth={2.2} {...props}>
      <path d="M17 3l3 3-3 3" />
      <path d="M4 12V9a3 3 0 0 1 3-3h13" />
      <path d="M7 21l-3-3 3-3" />
      <path d="M20 12v3a3 3 0 0 1-3 3H4" />
    </Mark>
  );
}

/** Report-a-problem affordance (replaces the flag glyph). */
export function FlagIcon(props: MarkProps) {
  return <Mark {...props}><path d="M5 21V4h14l-2.5 4L19 12H5" /></Mark>;
}

/** Tutor feature on the landing cards. */
export function AssistantIcon(props: MarkProps) {
  return (
    <Mark strokeWidth={1.9} {...props}>
      <path d="M21 12a8 8 0 0 1-8 8H7l-4 3V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8Z" />
      <path d="M8.5 12h.01M12 12h.01M15.5 12h.01" />
    </Mark>
  );
}

/** Weekly-plan feature on the landing cards. */
export function CalendarIcon(props: MarkProps) {
  return (
    <Mark strokeWidth={1.9} {...props}>
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <path d="M16 2v4M8 2v4M3 10h18" />
    </Mark>
  );
}

/** Mock-exam feature on the landing cards. */
export function TargetIcon(props: MarkProps) {
  return (
    <Mark strokeWidth={1.9} {...props}>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="4.5" />
      <path d="M12 12h.01" />
    </Mark>
  );
}

/** Settings affordance (replaces the gear glyph, which renders as an emoji box on some platforms). */
export function SettingsIcon(props: MarkProps) {
  return (
    <Mark strokeWidth={1.9} {...props}>
      <circle cx="12" cy="12" r="3.2" />
      <path d="M12 3.5v2.2M12 18.3v2.2M20.5 12h-2.2M5.7 12H3.5" />
      <path d="M18 6l-1.6 1.6M7.6 16.4 6 18M18 18l-1.6-1.6M7.6 7.6 6 6" />
    </Mark>
  );
}
