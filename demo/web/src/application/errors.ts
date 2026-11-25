/**
 * The API could not be reached, or it answered with a problem document.
 * `code` is the stable machine-readable name the screen decides from.
 */
export class ApiProblemError extends Error {
  readonly code: string;
  readonly title: string;
  readonly detail: string;

  constructor(problem: { code: string; title: string; detail: string }) {
    super(`${problem.title}: ${problem.detail}`);
    this.name = 'ApiProblemError';
    this.code = problem.code;
    this.title = problem.title;
    this.detail = problem.detail;
  }
}
