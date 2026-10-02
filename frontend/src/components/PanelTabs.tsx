import type { NavFn, Screen } from "../types";
import { PANELS, type PanelKey } from "../navConfig";

/** Sub-panel navigation: the flat tab row pinned to the top of every screen
 * inside a main panel (Ranked / Plan / Profile). Styled like the knowledge
 * graph tabs - accent underline on the active tab, no card pop-outs. */
export default function PanelTabs({ panelKey, screen, nav, isAdmin }: {
  panelKey: PanelKey;
  screen: Screen;
  nav: NavFn;
  isAdmin: boolean;
}) {
  const panel = PANELS[panelKey];
  const items = panel.items.filter(item => item.screen !== "admin" || isAdmin);
  return (
    <nav role="tablist" aria-label={`پنل ${panel.label}`}
      className="flex gap-1 overflow-x-auto bg-[var(--card)] border-b border-[var(--border)] px-3 pt-12">
      {items.map(item => {
        const active = screen === item.screen;
        return (
          <button key={item.screen} type="button" role="tab" aria-selected={active}
            onClick={() => nav(item.screen)}
            className={`shrink-0 whitespace-nowrap rounded-t-lg border-b-2 px-3 pb-2 pt-1.5 text-[13px] font-display transition-colors ${
              active
                ? "border-[var(--accent)] bg-[var(--accent-soft)] text-[var(--accent)]"
                : "border-transparent text-[var(--muted)] hover:text-[var(--text)]"
            }`}>
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
