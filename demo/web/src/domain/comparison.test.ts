import { describe, expect, it } from 'vitest';
import {
  comparisonColumns,
  initialLetters,
  olderRuleOf,
  packageCommits,
  type Comparison,
  type ComparedVersion,
  type FlatReference,
} from './comparison';

const version = (letter: string, over: Partial<ComparedVersion> = {}): ComparedVersion => ({
  id: `geneva-3km.v1.${letter}`,
  letter,
  name: `Version ${letter}`,
  goals: {},
  flatReference: 'flat-1',
  packageCommit: 'abcdef0123',
  packageFingerprint: 'fp',
  simulations: [
    { priceScheme: 'model_prices', ruleCurrent: true, ruleVersion: 1 },
    { priceScheme: 'flat', ruleCurrent: true, ruleVersion: 1 },
  ],
  solveKey: `solve-${letter}`,
  ...over,
});

const flat = (id: string, letters: string[]): FlatReference => ({
  id,
  letters,
  flatPrice: 1,
  fare: 2,
  parkingFee: 2.8,
  costBike: 0.6,
  ruleCurrent: true,
  ruleVersion: 1,
});

const comparison = (over: Partial<Comparison>): Comparison => ({
  instanceVersion: { id: 'geneva-3km.v1', name: 'Geneva 3 km v1' },
  period: { id: 'monday', name: 'Monday 08:00–09:00' },
  versions: [],
  flatReferences: [],
  groups: [],
  identicalSolves: [],
  ...over,
});

describe('the columns of a comparison', () => {
  it('puts each flat column first, then the versions it serves', () => {
    const columns = comparisonColumns(
      comparison({
        versions: [
          version('A', { flatReference: 'f1' }),
          version('B', { flatReference: 'f2' }),
          version('C', { flatReference: 'f1' }),
        ],
        flatReferences: [flat('f1', ['A', 'C']), flat('f2', ['B'])],
      }),
    );
    expect(
      columns.map((column) =>
        column.kind === 'flat' ? `flat ${column.reference.id}` : column.version.letter,
      ),
    ).toEqual(['flat f1', 'A', 'C', 'flat f2', 'B']);
  });
});

describe('the letters ticked when L-4 opens', () => {
  it('takes the first four finished letters in letter order', () => {
    expect(initialLetters(['C', 'A', 'B', 'E', 'D'], null)).toEqual(['A', 'B', 'C', 'D']);
    expect(initialLetters(['A', 'B', 'C'], 'B')).toEqual(['A', 'B', 'C']);
  });

  it('gives the open version the fourth place when it is not among the first four', () => {
    expect(initialLetters(['A', 'B', 'C', 'D', 'E'], 'E')).toEqual(['A', 'B', 'C', 'E']);
  });

  it('ignores an open letter that is not finished', () => {
    expect(initialLetters(['A', 'B', 'C', 'D', 'E'], 'Z')).toEqual(['A', 'B', 'C', 'D']);
  });
});

describe('what the notices read', () => {
  it('lists distinct seven-character commits in letter order', () => {
    const found = comparison({
      versions: [
        version('A', { packageCommit: '1111111aaaa' }),
        version('B', { packageCommit: '2222222bbbb' }),
        version('C', { packageCommit: '1111111cccc' }),
        version('D', { packageCommit: null }),
      ],
    });
    expect(packageCommits(found)).toEqual(['1111111', '2222222']);
  });

  it('finds the rule version of an older simulation', () => {
    expect(olderRuleOf(version('A'))).toBeNull();
    expect(
      olderRuleOf(
        version('A', {
          simulations: [{ priceScheme: 'flat', ruleCurrent: false, ruleVersion: 1 }],
        }),
      ),
    ).toBe(1);
  });
});
