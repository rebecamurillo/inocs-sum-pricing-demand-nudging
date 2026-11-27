import { versionTag } from './l1-text';

export const DELETE_LABEL = 'Delete…';
export const KEEP = 'Keep';
export const RUN_ACTIVE_NOTE = 'A run of this version is queued or running.';

export function versionDeleteQuestion(name: string, number: number): string {
  return `Delete ${name} ${versionTag(number)}? This removes the instance version. Other versions of ${name} stay. This cannot be undone.`;
}

export function versionDeleteAction(number: number): string {
  return `Delete ${versionTag(number)}`;
}

export function instanceDeleteQuestion(name: string, numbers: readonly number[]): string {
  const tags = [...numbers]
    .sort((a, b) => a - b)
    .map(versionTag)
    .join(', ');
  const count = numbers.length === 1 ? '1 version' : `${String(numbers.length)} versions`;
  return `Delete ${name}? This removes its ${count} (${tags}). This cannot be undone.`;
}

export function instanceDeleteAction(name: string): string {
  return `Delete ${name} and its versions`;
}
