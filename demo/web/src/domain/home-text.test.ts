import { describe, expect, it } from 'vitest';
import { MODEL_AUTHOR, MODEL_AUTHOR_IS_PLACEHOLDER } from './footer';
import { limitsLine, NO_SHOWCASE_TEXT, SHOWCASE_ERROR_TEXT } from './home-text';

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
