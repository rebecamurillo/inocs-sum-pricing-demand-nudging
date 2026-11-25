import { describe, expect, it } from 'vitest';
import { ApiProblemError } from './errors';

describe('ApiProblemError', () => {
  it('carries the code, title and detail of the problem', () => {
    const error = new ApiProblemError({
      code: 'component_unavailable',
      title: 'The trip planner is not reachable',
      detail: 'No answer within 2 s.',
    });

    expect(error).toBeInstanceOf(Error);
    expect(error.name).toBe('ApiProblemError');
    expect(error.code).toBe('component_unavailable');
    expect(error.title).toBe('The trip planner is not reachable');
    expect(error.detail).toBe('No answer within 2 s.');
    expect(error.message).toBe('The trip planner is not reachable: No answer within 2 s.');
  });
});
