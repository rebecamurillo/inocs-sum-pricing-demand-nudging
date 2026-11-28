/** Exact statement from the team folder (knowledge/visual-identity.md § Sources). */
export const FUNDING_STATEMENT = 'Funded by the European Union under Horizon Europe, project SUM.';

/** The model's author, shown as a placeholder until the maintainer supplies the name. */
export const MODEL_AUTHOR = 'placeholder';
export const MODEL_AUTHOR_IS_PLACEHOLDER = true;

/** "Run unmodified." is not shipped until the author accepts it (Q-40). */
export const RUN_UNMODIFIED = 'Run unmodified.';
export const RUN_UNMODIFIED_CONFIRMED = false;

export interface ModelSourceLine {
  readonly before: string;
  readonly author: string;
  readonly authorIsPlaceholder: boolean;
  readonly after: string;
}

/** The line in parts, so the presentation can mark the author while it is a placeholder. */
export function modelSourceLine(runUnmodified: boolean): ModelSourceLine {
  return {
    before: 'Pricing model: ',
    author: MODEL_AUTHOR,
    authorIsPlaceholder: MODEL_AUTHOR_IS_PLACEHOLDER,
    after: `, Inria INOCS.${runUnmodified ? ` ${RUN_UNMODIFIED}` : ''}`,
  };
}
