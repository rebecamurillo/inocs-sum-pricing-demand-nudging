import { describe, expect, it } from 'vitest';
import {
  DELETE_LABEL,
  KEEP,
  RUN_ACTIVE_NOTE,
  instanceDeleteAction,
  instanceDeleteQuestion,
  versionDeleteAction,
  versionDeleteQuestion,
} from './delete-text';

describe('the wording of the deletions', () => {
  it('names what a version deletion removes', () => {
    expect(versionDeleteQuestion('Geneva 3 km', 1)).toBe(
      'Delete Geneva 3 km v1? This removes the instance version. Other versions of Geneva 3 km stay. This cannot be undone.',
    );
    expect(versionDeleteAction(2)).toBe('Delete v2');
  });

  it('names the versions an instance deletion removes, one or several', () => {
    expect(instanceDeleteQuestion('Geneva 3 km', [1])).toBe(
      'Delete Geneva 3 km? This removes its 1 version (v1). This cannot be undone.',
    );
    expect(instanceDeleteQuestion('Geneva 3 km', [3, 1, 2])).toBe(
      'Delete Geneva 3 km? This removes its 3 versions (v1, v2, v3). This cannot be undone.',
    );
    expect(instanceDeleteAction('Geneva 3 km')).toBe('Delete Geneva 3 km and its versions');
  });

  it('names the pricing versions a version deletion removes, one or several', () => {
    expect(versionDeleteQuestion('Geneva 3 km', 1, ['A'])).toBe(
      'Delete Geneva 3 km v1? This removes the instance version and its 1 pricing version with its result (A). Other versions of Geneva 3 km stay. This cannot be undone.',
    );
    expect(versionDeleteQuestion('Geneva 3 km', 1, ['A', 'B', 'C'])).toBe(
      'Delete Geneva 3 km v1? This removes the instance version and its 3 pricing versions with their results (A, B, C). Other versions of Geneva 3 km stay. This cannot be undone.',
    );
    expect(versionDeleteAction(1, 1)).toBe('Delete v1 and its 1 pricing version');
    expect(versionDeleteAction(1, 2)).toBe('Delete v1 and its 2 pricing versions');
  });

  it('names the pricing versions an instance deletion removes', () => {
    expect(instanceDeleteQuestion('Geneva 3 km', [1, 2], 5)).toBe(
      'Delete Geneva 3 km? This removes its 2 versions (v1, v2) and their 5 pricing versions with their results. This cannot be undone.',
    );
    expect(instanceDeleteQuestion('Geneva 3 km', [1], 1)).toBe(
      'Delete Geneva 3 km? This removes its 1 version (v1) and their 1 pricing version with its result. This cannot be undone.',
    );
    expect(instanceDeleteQuestion('Geneva 3 km', [1], 0)).toBe(
      'Delete Geneva 3 km? This removes its 1 version (v1). This cannot be undone.',
    );
  });

  it('has the labels and the refusal note', () => {
    expect(DELETE_LABEL).toBe('Delete…');
    expect(KEEP).toBe('Keep');
    expect(RUN_ACTIVE_NOTE).toBe('A run of this version is queued or running.');
  });
});
