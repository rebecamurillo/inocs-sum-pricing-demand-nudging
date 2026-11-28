import { describe, expect, it } from 'vitest';
import type { PricingVersionState } from './pricing-version';
import {
  ON_THE_HOME_PAGE,
  SHOWCASE_NOT_SET,
  showcaseActionShown,
  showcaseHeldNote,
  USE_ON_HOME_PAGE,
  homeTitle,
} from './showcase-text';

describe('showcase texts', () => {
  it('words the action, its two hover texts and the link', () => {
    expect(USE_ON_HOME_PAGE).toBe('Use on the home page');
    expect(ON_THE_HOME_PAGE).toBe('On the home page');
    expect(homeTitle(null)).toBe("Shows this version's result on the home page.");
    expect(homeTitle('A')).toBe(
      "Shows this version's result on the home page, in place of Version A's.",
    );
  });

  it('words the failure and the deletion note', () => {
    expect(SHOWCASE_NOT_SET).toBe("Not set: the demonstrator's API did not answer.");
    expect(showcaseHeldNote('B', 'Geneva 3 km v1')).toBe(
      "Version B of Geneva 3 km v1 is the home page's result: choose another one first.",
    );
  });
});

describe('showcaseActionShown', () => {
  const held = { pricingVersionId: 'geneva-3km.v1.B' };

  it.each<[PricingVersionState, boolean]>([
    ['draft', false],
    ['running', false],
    ['queued', false],
    ['failed', false],
    ['cancelled', false],
    ['result', true],
  ])('for state %s with no showcase: %s', (state, shown) => {
    expect(showcaseActionShown(state, 'geneva-3km.v1.A', null)).toBe(shown);
  });

  it('shows for a result that is not the showcase and hides for the showcase itself', () => {
    expect(showcaseActionShown('result', 'geneva-3km.v1.A', held)).toBe(true);
    expect(showcaseActionShown('result', 'geneva-3km.v1.B', held)).toBe(false);
  });
});
