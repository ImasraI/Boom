import { DayRecord } from "./types";

export const MAJORS = [
  "ریاضی فیزیک",
  "علوم تجربی",
  "علوم انسانی",
  "هنر",
  "زبان‌های خارجی",
];

export const GRADES = ["دهم", "یازدهم", "دوازدهم", "فارغ‌التحصیل"];
export const STUDY_HOURS_OPTIONS = [
  "۱ تا ۲ ساعت", "۲ تا ۳ ساعت", "۳ تا ۴ ساعت", "۴ تا ۶ ساعت", "۶ تا ۸ ساعت", "بیش از ۸ ساعت",
];
export const TEST_EXAM_OPTIONS = [
  "قلم‌چی", "ماز", "گاج", "سنجش", "خیلی سبز",
];

export const SUBJECTS_BY_MAJOR: Record<string, string[]> = {
  "ریاضی فیزیک": [
    "حسابان", "جبر و گسسته", "هندسه", "فیزیک", "شیمی",
    "ادبیات فارسی", "عربی", "دین و زندگی", "زبان انگلیسی",
  ],
  "علوم تجربی": [
    "ریاضی", "فیزیک", "شیمی", "زیست‌شناسی",
    "ادبیات فارسی", "عربی", "دین و زندگی", "زبان انگلیسی",
  ],
  "علوم انسانی": [
    "ادبیات فارسی", "عربی", "تاریخ", "جغرافیا", "اقتصاد",
    "منطق و فلسفه", "دین و زندگی", "علوم اجتماعی", "ریاضی و آمار",
  ],
  "هنر": [
    "نقاشی و هنرهای تجسمی", "ترکیب‌بندی", "تاریخ هنر",
    "ادبیات فارسی", "زبان انگلیسی", "ریاضی",
  ],
  "زبان‌های خارجی": [
    "زبان انگلیسی", "زبان دوم", "ادبیات فارسی", "ریاضی", "تاریخ",
  ],
};

export const PAST_RECORDS: DayRecord[] = [
  { date: "2026-08-20", tasksTotal: 5, tasksDone: 4, xp: 180 },
  { date: "2026-08-21", tasksTotal: 4, tasksDone: 4, xp: 200 },
  { date: "2026-08-22", tasksTotal: 6, tasksDone: 3, xp: 120 },
  { date: "2026-08-23", tasksTotal: 5, tasksDone: 5, xp: 250 },
  { date: "2026-08-24", tasksTotal: 4, tasksDone: 2, xp: 80 },
  { date: "2026-08-25", tasksTotal: 5, tasksDone: 4, xp: 180 },
  { date: "2026-08-26", tasksTotal: 5, tasksDone: 1, xp: 40 },
];

export const SUBJECT_COLORS: Record<string, string> = {
  "حسابان": "var(--syntax-blue)",
  "ریاضی": "var(--syntax-blue)",
  "جبر": "var(--syntax-blue)",
  "هندسه": "var(--syntax-cyan)",
  "فیزیک": "var(--syntax-teal)",
  "شیمی": "var(--syntax-purple)",
  "زیست": "var(--syntax-green)",
  "ادبیات": "var(--syntax-yellow)",
  "عربی": "var(--syntax-orange)",
  "انگلیسی": "var(--syntax-magenta)",
  "زبان انگلیسی": "var(--syntax-magenta)",
  "دین": "var(--syntax-orange)",
  "تاریخ": "var(--brown-text)",
  "جغرافیا": "var(--syntax-teal)",
  "اقتصاد": "var(--syntax-green)",
  "منطق": "var(--syntax-purple)",
  "اجتماعی": "var(--syntax-cyan)",
  "default": "var(--muted-2)",
};
