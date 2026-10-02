import { loadDoneSkipped, homeTasksForDate } from "./homeTasks";
import { addDays, toISO } from "./scheduleStore";

export function studyRecords(today = new Date()) {
  return Array.from({ length: 7 }, (_, i) => {
    const date = toISO(addDays(today, i - 6));
    const tasksDone = loadDoneSkipped(date).done.length;
    return { date, tasksDone, tasksTotal: Math.max(tasksDone, homeTasksForDate(date).length), xp: tasksDone * 10 };
  });
}

export function currentStreak(today = new Date()) {
  let day = today;
  if (!loadDoneSkipped(toISO(day)).done.length) day = addDays(day, -1);
  let streak = 0;
  while (streak < 366 && loadDoneSkipped(toISO(day)).done.length) {
    streak++; day = addDays(day, -1);
  }
  return streak;
}
