import type { Screen } from "../types";
import { PANELS, panelOf } from "../navConfig";
import { StudySymbol } from "./StudySymbols";

export default function Workbench({ screen, onSettings }: { screen: Screen; onSettings: () => void }) {
  const current = Object.values(PANELS).flatMap(panel => panel.items).find(item => item.screen === screen);
  return <header className="workbench-bar">
    <div className="workbench-breadcrumb"><StudySymbol kind="plan" size={16} /><span>بوم</span><b aria-hidden="true">/</b><span>{panelOf(screen)?.label || "میز مطالعه"}</span>{current && current.label !== panelOf(screen)?.label && <><b aria-hidden="true">/</b><strong>{current.label}</strong></>}</div>
    <button className="workbench-settings" onClick={onSettings} aria-label="باز کردن تنظیمات">
      <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"><path d="m9 3 1-1h4l1 1 .5 2 2 .8 1.8-.6 2 3.4-.4 1.3-1.5 1.5v2.2l1.5 1.5.4 1.3-2 3.4-1.8-.6-2 .8-.5 2-1 1h-4l-1-1-.5-2-2-.8-1.8.6-2-3.4.4-1.3L4.6 13v-2.2L3.1 9.3l-.4-1.3 2-3.4 1.8.6 2-.8Z"/><circle cx="12" cy="12" r="3"/></svg>
      <span>تنظیمات</span>
    </button>
  </header>;
}
