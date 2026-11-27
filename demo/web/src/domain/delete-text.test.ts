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

  it('has the labels and the refusal note', () => {
    expect(DELETE_LABEL).toBe('Delete…');
    expect(KEEP).toBe('Keep');
    expect(RUN_ACTIVE_NOTE).toBe('A run of this version is queued or running.');
  });
});
