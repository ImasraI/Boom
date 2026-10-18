/** Classify by activity identity rather than the old saved color. */
export const CLASS_COLOR = '#C96D68';
export const MOCK_COLOR = '#98CAE1';
export const PRACTICE_COLOR = '#9B7AAD';

type Activity = { type: string; source_ref?: string; subject?: string; task_type?: string; color?: string };

export function scheduleActivity(block: Activity): 'class' | 'mock' | 'practice' | 'other' {
  if (block.type === 'class') return 'class';
  if (block.source_ref === 'weekly-mock' || block.task_type === 'mock'
      || (block.type === 'test' && block.subject === 'آزمون')) return 'mock';
  if (block.type === 'test' || block.task_type === 'practice') return 'practice';
  return 'other';
}

export function scheduleColor(block: Activity): string {
  const kind = scheduleActivity(block);
  return kind === 'class' ? CLASS_COLOR : kind === 'mock' ? MOCK_COLOR
    : kind === 'practice' ? PRACTICE_COLOR : block.color || 'var(--syntax-yellow)';
}
