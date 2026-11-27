import { MODEL_AUTHOR, MODEL_AUTHOR_IS_PLACEHOLDER, type ModelSourceLine } from './footer';

/** The line under Home's cards, in parts so the presentation can mark the author while it is a placeholder. */
export function limitsLine(runUnmodified: boolean): ModelSourceLine {
  return {
    before: 'A research model by ',
    author: MODEL_AUTHOR,
    authorIsPlaceholder: MODEL_AUTHOR_IS_PLACEHOLDER,
    after: `, Inria INOCS, ${runUnmodified ? 'run unmodified' : 'run'} on one zone of Geneva with simulated demand. The figure above comes from the model's prices and a simulation of travellers, not from a trial in the street.`,
  };
}

/** The visual's text when no result is marked for the home page (the API's 404). */
export const NO_SHOWCASE_TEXT =
  'No result on this page yet. In the Lab, open the result of a pricing version and choose "Use on the home page".';

/** The visual's text when the showcase could not be read. */
export const SHOWCASE_ERROR_TEXT =
  "The result could not be loaded: the demonstrator's API did not answer.";
