import { describe, expect, it } from 'vitest';
import { MODEL_AUTHOR, MODEL_AUTHOR_IS_PLACEHOLDER } from './footer';
import {
  HOME_MAP_LEGEND,
  limitsLine,
  NO_SHOWCASE_TEXT,
  PROVISIONAL_LINE,
  SHOWCASE_ERROR_TEXT,
  showcaseFigure,
  showcaseLine,
  showcaseScope,
  showcaseSourceLine,
} from './home-text';

const join = (line: ReturnType<typeof limitsLine>) => `${line.before}${line.author}${line.after}`;

describe('limitsLine', () => {
  it('reads "run on" while the author has not accepted "run unmodified"', () => {
    expect(join(limitsLine(false))).toBe(
      `A research model by ${MODEL_AUTHOR}, Inria INOCS, run on one zone of Geneva with simulated demand. The figure above comes from the model's prices and a simulation of travellers, not from a trial in the street.`,
    );
  });

  it('reads "run unmodified on" with the flag on', () => {
    expect(limitsLine(true).after).toMatch(/^, Inria INOCS, run unmodified on one zone of Geneva /);
  });

  it('takes the author and its placeholder state from the footer constants', () => {
    const line = limitsLine(false);
    expect(line.author).toBe(MODEL_AUTHOR);
    expect(line.authorIsPlaceholder).toBe(MODEL_AUTHOR_IS_PLACEHOLDER);
  });
});

describe('the visual texts', () => {
  it('say what is missing and what to do', () => {
    expect(NO_SHOWCASE_TEXT).toBe(
      'No result on this page yet. In the Lab, open the result of a pricing version and choose "Use on the home page".',
    );
    expect(SHOWCASE_ERROR_TEXT).toBe(
      "The result could not be loaded: the demonstrator's API did not answer.",
    );
  });
});

describe('showcaseFigure', () => {
  it('rounds half away from zero, as the result view does', () => {
    expect(showcaseFigure(2.5)).toBe(3);
    expect(showcaseFigure(-2.5)).toBe(-3);
    expect(showcaseFigure(10.005)).toBe(10);
    expect(showcaseFigure(0.4)).toBe(0);
    expect(showcaseFigure(-0.4)).toBe(0);
  });
});

describe('showcaseLine', () => {
  it('says fewer car trips above 0', () => {
    expect(showcaseLine(4, 1)).toBe(
      '4 fewer car trips for every 100 simulated travellers, against a flat bike price of 1.00 CHF',
    );
  });

  it('says one car trip for 1', () => {
    expect(showcaseLine(1, 0.6)).toBe(
      '1 fewer car trip for every 100 simulated travellers, against a flat bike price of 0.60 CHF',
    );
    expect(showcaseLine(-1, 0.6)).toBe(
      '1 more car trip for every 100 simulated travellers, against a flat bike price of 0.60 CHF',
    );
  });

  it('says more car trips below 0, without a sign', () => {
    expect(showcaseLine(-3, 1.25)).toBe(
      '3 more car trips for every 100 simulated travellers, against a flat bike price of 1.25 CHF',
    );
  });

  it('says as many car trips at 0', () => {
    expect(showcaseLine(0, 1)).toBe(
      '0: as many car trips as with a flat bike price of 1.00 CHF, for every 100 simulated travellers',
    );
  });
});

describe('the tile texts', () => {
  it('writes the source line, with the older rule when it is stale', () => {
    expect(showcaseSourceLine(true, 1)).toBe(
      'Simulated travellers \u00b7 placeholder rule: half price, half travel time',
    );
    expect(showcaseSourceLine(false, 1)).toBe(
      'Simulated travellers \u00b7 placeholder rule: half price, half travel time \u00b7 older rule (v1)',
    );
  });

  it('writes the scope', () => {
    expect(showcaseScope('Geneva', 3, 'Monday 08:00\u201309:00', 'B', 'Geneva 3 km v1')).toBe(
      'Geneva, 3 km zone, Monday 08:00\u201309:00 \u00b7 Version B of Geneva 3 km v1',
    );
  });

  it('carries the provisional line and the legend as written', () => {
    expect(PROVISIONAL_LINE).toBe(
      "Provisional: the model's author has not yet validated the simulation's rule or the claims of this page.",
    );
    expect(HOME_MAP_LEGEND).toBe(
      "Each line: a trip between two hubs by public transport + shared bike, the only trips the pricing model prices. Colour: mean bike price, low to high \u00b7 width: bike rides. Computed from the model's flows.",
    );
  });
});
