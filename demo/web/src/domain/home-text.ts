import { olderRuleSuffix } from './older-rule-text';
import { roundHalfAway, SIMULATION_SOURCE } from './result-text';
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

export const PROVISIONAL_LINE =
  "Provisional: the model's author has not yet validated the simulation's rule or the claims of this page.";

export const HOME_MAP_LEGEND =
  "Each line: a trip between two hubs by public transport + shared bike, the only trips the pricing model prices. Colour: mean bike price, low to high \u00b7 width: bike rides. Computed from the model's flows.";

/** The figure of the stat tile: the difference in points, rounded as the result view's title is. */
export function showcaseFigure(differencePoints: number): number {
  return roundHalfAway(differencePoints);
}

/** The tile's line under the figure; the flat price is formatted with two decimals. */
export function showcaseLine(figure: number, flatPrice: number): string {
  const price = `${flatPrice.toFixed(2)} CHF`;
  if (figure === 0) {
    return `0: as many car trips as with a flat bike price of ${price}, for every 100 simulated travellers`;
  }
  const count = Math.abs(figure);
  const what =
    figure > 0
      ? count === 1
        ? '1 fewer car trip'
        : `${String(count)} fewer car trips`
      : count === 1
        ? '1 more car trip'
        : `${String(count)} more car trips`;
  return `${what} for every 100 simulated travellers, against a flat bike price of ${price}`;
}

/** The source line of the tile: the simulation's rule, and the older rule when it is stale. */
export function showcaseSourceLine(ruleCurrent: boolean, ruleVersion: number): string {
  return ruleCurrent ? SIMULATION_SOURCE : `${SIMULATION_SOURCE}${olderRuleSuffix(ruleVersion)}`;
}

export function showcaseScope(
  city: string,
  radiusKm: number,
  periodLabel: string,
  letter: string,
  instanceVersionName: string,
): string {
  return `${city}, ${String(radiusKm)} km zone, ${periodLabel} \u00b7 Version ${letter} of ${instanceVersionName}`;
}
