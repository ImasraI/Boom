import type { Screen } from "./types";

/** Sub-panel definitions for the app's 3 main panels. The bottom tab bar
 * (phone) and the grouped desktop sidebar are built from these; PanelTabs
 * renders the sub-navigation row shown at the top of every panel screen. */
export interface NavItem {
  screen: Screen;
  label: string;
}

export type PanelKey = "ranked" | "plan" | "profile";

export interface PanelDef {
  key: PanelKey;
  label: string;
  items: NavItem[];
}

export const PANELS: Record<PanelKey, PanelDef> = {
  ranked: {
    key: "ranked",
    label: "مسابقه",
    items: [
      { screen: "arena", label: "مسابقه رنک‌دار" },
      { screen: "mock", label: "آزمون هوشمند" },
      { screen: "leaderboard", label: "جدول امتیازات" },
    ],
  },
  plan: {
    key: "plan",
    label: "برنامه",
    items: [
      { screen: "schedule", label: "برنامه هفتگی" },
      { screen: "plan", label: "برنامه" },
      { screen: "knowledge", label: "نقشه یادگیری" },
      { screen: "exams", label: "آزمون‌ها" },
    ],
  },
  profile: {
    key: "profile",
    label: "پروفایل",
    items: [
      { screen: "profile", label: "پروفایل" },
      { screen: "streak", label: "استریک" },
      { screen: "evaluation", label: "ارزیابی" },
      { screen: "recovery", label: "ریکاوری" },
      { screen: "admin", label: "مدیریت" },
    ],
  },
};

/** The panel a screen belongs to, or null for screens outside all panels
 * (home, chat, auth). */
export function panelOf(screen: Screen): PanelDef | null {
  return (Object.values(PANELS) as PanelDef[]).find(panel =>
    panel.items.some(item => item.screen === screen),
  ) ?? null;
}
