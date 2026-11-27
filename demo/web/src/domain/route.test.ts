import { describe, expect, it } from 'vitest';
import { compareRoute, parseRoute, serialiseRoute, type LabRoute } from './route';

const instance = { instanceId: 'geneva-3km', version: 2 };

const valid: readonly [string, LabRoute][] = [
  ['#/lab', { kind: 'lab', period: null }],
  ['#/lab/geneva-3km.v2', { kind: 'instance', instance, period: null }],
  ['#/lab/geneva-3km.v2/pricing/B', { kind: 'pricing', instance, letter: 'B', period: null }],
  ['#/lab/geneva-3km.v2/result/AB', { kind: 'result', instance, letter: 'AB', period: null }],
  [
    '#/lab/geneva-3km.v2/compare/A,B,C',
    { kind: 'compare', instance, letters: ['A', 'B', 'C'], period: null },
  ],
  ['#/lab/traveller/geneva-3km.v2/B', { kind: 'traveller', instance, letter: 'B', period: null }],
];

describe('parseRoute and serialiseRoute', () => {
  it.each(valid)('%s round-trips', (hash, route) => {
    expect(parseRoute(hash)).toEqual(route);
    expect(serialiseRoute(route)).toBe(hash);
  });

  it.each(valid)('%s keeps an optional period', (hash, route) => {
    const withPeriod = `${hash}?period=mon-08:00`;
    expect(parseRoute(withPeriod)).toEqual({ ...route, period: 'mon-08:00' });
    expect(serialiseRoute(parseRoute(withPeriod) as LabRoute)).toBe(withPeriod);
  });

  it.each([
    '',
    '#',
    '#/',
    '#/play',
    '#/lab/',
    '#/lab/geneva-3km',
    '#/lab/geneva-3km.v0',
    '#/lab/geneva-3km.v01',
    '#/lab/geneva-3km.v1/pricing/b',
    '#/lab/geneva-3km.v1/compare/A',
    '#/lab/geneva-3km.v1/compare/A,A',
    '#/lab/geneva-3km.v1/compare/A,B,C,D,E',
    '#/lab?other=1',
    '#/lab?period=',
    '#/lab?period=a&period=b',
    '#/lab/geneva-3km.v1/result/A/extra',
    '#/lab/Geneva.v1',
    'lab',
    '#/labx',
    '#/lab?period=a?period=b',
    '#/lab/geneva-3km.v1/pricing',
    '#/lab/geneva-3km.v1/pricing/b',
    '#/lab/geneva-3km.v1/other/B',
    '#/lab/geneva-3km.v1/compare/a,b',
    '#/lab/traveller',
    '#/lab/traveller/geneva-3km.v1',
    '#/lab/traveller/geneva-3km.v1/b',
    '#/lab/traveller/nope/B',
    '#/lab/traveller/geneva-3km.v1/B/x',
  ])('reads %j as unparsable', (hash) => {
    expect(parseRoute(hash)).toEqual({ kind: 'unparsable' });
  });
});

describe('the compare route', () => {
  it('writes its letters in letter order, each once, for two to four versions', () => {
    for (const [given, written] of [
      [['B', 'A'], '#/lab/geneva-3km.v2/compare/A,B'],
      [['C', 'A', 'B'], '#/lab/geneva-3km.v2/compare/A,B,C'],
      [['D', 'B', 'C', 'A'], '#/lab/geneva-3km.v2/compare/A,B,C,D'],
      [['B', 'A', 'B'], '#/lab/geneva-3km.v2/compare/A,B'],
    ] as const) {
      expect(serialiseRoute(compareRoute(instance, given, null))).toBe(written);
    }
  });

  it('keeps the period and parses back what it wrote', () => {
    const route = compareRoute(instance, ['C', 'A'], 'monday');
    expect(serialiseRoute(route)).toBe('#/lab/geneva-3km.v2/compare/A,C?period=monday');
    expect(parseRoute(serialiseRoute(route))).toEqual(route);
  });
});
