import { versionTag } from './l1-text';

export const DELETE_LABEL = 'Delete…';
export const KEEP = 'Keep';
export const RUN_ACTIVE_NOTE = 'A run of this version is queued or running.';

function pricingVersions(count: number): string {
  return count === 1 ? '1 pricing version' : `${String(count)} pricing versions`;
}

/** The pricing versions (their letters) that go with the instance version are named when there are any. */
export function versionDeleteQuestion(
  name: string,
  number: number,
  letters: readonly string[] = [],
): string {
  const removes =
    letters.length === 0
      ? 'the instance version'
      : `the instance version and its ${pricingVersions(letters.length)} with ${letters.length === 1 ? 'its result' : 'their results'} (${letters.join(', ')})`;
  return `Delete ${name} ${versionTag(number)}? This removes ${removes}. Other versions of ${name} stay. This cannot be undone.`;
}

export function versionDeleteAction(number: number, pricingCount = 0): string {
  return pricingCount === 0
    ? `Delete ${versionTag(number)}`
    : `Delete ${versionTag(number)} and its ${pricingVersions(pricingCount)}`;
}

export function instanceDeleteQuestion(
  name: string,
  numbers: readonly number[],
  pricingCount = 0,
): string {
  const tags = [...numbers]
    .sort((a, b) => a - b)
    .map(versionTag)
    .join(', ');
  const count = numbers.length === 1 ? '1 version' : `${String(numbers.length)} versions`;
  const pricing =
    pricingCount === 0
      ? ''
      : ` and their ${pricingVersions(pricingCount)} with ${pricingCount === 1 ? 'its result' : 'their results'}`;
  return `Delete ${name}? This removes its ${count} (${tags})${pricing}. This cannot be undone.`;
}

export function instanceDeleteAction(name: string): string {
  return `Delete ${name} and its versions`;
}
