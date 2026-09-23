export type Screen =
  | "landing" | "login" | "signup" | "home"
  | "streak" | "recovery" | "exams" | "plan" | "chat" | "profile" | "schedule" | "evaluation"
  | "mock" | "arena" | "admin";

export interface SignupData {
  name: string;
  major: string;
  grade: string;
  examYear: string;
  targetRank: string;
  studyHours: string;
  testExams: string[];
  phone: string;
  birthday?: string;
  city?: string;
  school?: string;
  wakeTime?: string;
  dailyHours?: Record<string, number>;
  maxConsec?: number;
  breakStyle?: string;
  sleepHours?: number;
  environment?: string;
  phoneUsage?: string;
  completion?: Record<string, number>;
  confidence?: Record<string, number>;
  strictness?: string;
  difficulty?: string;
  studyStyle?: string;
  reminderTime?: string;
  notifs?: boolean;
}

export interface Task {
  id: number;
  type: "study" | "test" | "quiz" | "review" | "practice";
  title: string;
  description: string;
  subject: string;
  duration: string;
  scheduledTime: string;
  done: boolean;
}

export interface DayRecord {
  date: string;
  tasksTotal: number;
  tasksDone: number;
  xp: number;
}

export type NavFn = (screen: Screen) => void;

export function emptySignupData(phone = ""): SignupData {
  return {
    name: "",
    phone,
    major: "",
    grade: "",
    examYear: "",
    targetRank: "",
    studyHours: "",
    testExams: [],
  };
}

/** Merge stored profile for a phone; never keep a password field. */
export function normalizeSignupData(raw: unknown, phoneFallback = ""): SignupData {
  const base = emptySignupData(phoneFallback);
  if (!raw || typeof raw !== "object") return base;
  const d = raw as Record<string, any>;
  return {
    ...base,
    ...d,
    phone: typeof d.phone === "string" ? d.phone : phoneFallback,
    testExams: Array.isArray(d.testExams) ? d.testExams.filter((x): x is string => typeof x === "string") : [],
  };
}
