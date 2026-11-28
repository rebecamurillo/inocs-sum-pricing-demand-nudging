import type { PricingVersionState } from './pricing-version';

export const USE_ON_HOME_PAGE = 'Use on the home page';
export const ON_THE_HOME_PAGE = 'On the home page';
export const SHOWCASE_NOT_SET = "Not set: the demonstrator's API did not answer.";

/** The hover text of "Use on the home page"; `showcaseLetter` is the letter of the version it would replace. */
export function homeTitle(showcaseLetter: string | null): string {
  return showcaseLetter === null
    ? "Shows this version's result on the home page."
    : `Shows this version's result on the home page, in place of Version ${showcaseLetter}'s.`;
}

/** What shows instead of a confirmation when "Delete…" is chosen on what holds the showcase. */
export function showcaseHeldNote(letter: string, instanceVersionName: string): string {
  return `Version ${letter} of ${instanceVersionName} is the home page's result: choose another one first.`;
}

/** "Use on the home page" shows only on a finished version that is not the showcase already. */
export function showcaseActionShown(
  state: PricingVersionState,
  versionId: string,
  showcase: { readonly pricingVersionId: string } | null,
): boolean {
  return state === 'result' && showcase?.pricingVersionId !== versionId;
}

/** The note of a refused deletion when the showcase could not be read to name its version. */
export const SHOWCASE_HELD_FALLBACK =
  "A version of this is the home page's result: choose another one first.";
