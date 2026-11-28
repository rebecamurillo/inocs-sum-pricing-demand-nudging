import { describe, expect, it } from 'vitest';
import type { BuildPlan, PlannedStep, RuleResult } from './city-instance';
import {
  BANNER_TEXTS,
  causeRows,
  changeRows,
  discardQuestion,
  draftHeading,
  draftSaved,
  inputText,
  measuredSentence,
  oneDraftMessage,
  parseInput,
  primaryLabel,
  primaryState,
  ruleFields,
  ruleLine,
  routingDateLine,
  saveBox,
  valueText,
  versionNumberOf,
  bannerSentences,
} from './draft-text';

function step(number: number, action: 'kept' | 'rebuilt', lastDurationS: number | null = null) {
  const names = ['area', 'hubs', 'routes', 'travellers_and_bikes'] as const;
  return {
    step: names[number - 1],
    number,
    action,
    causes: action === 'rebuilt' ? [{ kind: 'parameter', parameters: [] }] : [],
    lastDurationS,
  } as PlannedStep;
}

function plan(actions: ('kept' | 'rebuilt')[], durations: (number | null)[] = []): BuildPlan {
  return {
    steps: actions.map((action, at) => step(at + 1, action, durations[at] ?? null)),
    verdict: { allowed: true, reasons: [] },
  };
}

const rule = (
  id: string,
  passed: boolean,
  a: RuleResult['values'][0],
  b: RuleResult['values'][1],
): RuleResult => ({ rule: id, passed, values: [a, b] });

describe('draft sentences', () => {
  it('writes the heading, the saved time and the discard questions', () => {
    expect(draftHeading('Geneva 3 km')).toBe('Geneva 3 km · new version (draft)');
    expect(draftSaved(new Date(2026, 10, 27, 9, 5))).toBe('Draft saved · 09:05');
    expect(discardQuestion(1)).toBe(
      'Discard this draft? Its values are removed; v1 stays as it is.',
    );
    expect(discardQuestion(null)).toBe('Discard this draft? Its values are removed.');
    expect(primaryLabel(1)).toBe('Save as v1 and build');
    expect(primaryLabel(2)).toBe('Save and build');
  });

  it('writes the one-draft message with the creation day', () => {
    expect(oneDraftMessage(1, new Date('2026-11-24T10:00:00Z'))).toBe(
      'This instance already has a draft, started from v1 on 24 Nov. Continue it, or discard it first.',
    );
  });
});

describe('versionNumberOf', () => {
  it('reads the number of a version id', () => {
    expect(versionNumberOf('geneva-3km.v2')).toBe(2);
    expect(versionNumberOf('geneva-3km.v12')).toBe(12);
    expect(versionNumberOf('geneva-3km')).toBeNull();
  });
});

describe('the save box', () => {
  const box = (actions: ('kept' | 'rebuilt')[], versions = 3) =>
    saveBox('Geneva 3 km', 2, 1, versions, plan(actions));

  it('lists the rebuilt steps and the one kept step', () => {
    expect(box(['kept', 'rebuilt', 'rebuilt', 'rebuilt'])).toBe(
      'Saving creates Geneva 3 km v2. v1 and its 3 pricing versions stay as they are. Will rebuild: 2 Hubs, 3 Routes, 4 Travellers and bikes; step 1 is kept.',
    );
  });

  it('names two and three kept steps', () => {
    expect(box(['kept', 'kept', 'rebuilt', 'rebuilt'])).toContain(
      'Will rebuild: 3 Routes, 4 Travellers and bikes; steps 1 and 2 are kept.',
    );
    expect(box(['kept', 'kept', 'kept', 'rebuilt'])).toContain(
      'Will rebuild: 4 Travellers and bikes; steps 1, 2 and 3 are kept.',
    );
  });

  it('omits the clause when nothing is kept and says none when everything is', () => {
    expect(box(['rebuilt', 'rebuilt', 'rebuilt', 'rebuilt'])).toContain(
      'Will rebuild: 1 Area, 2 Hubs, 3 Routes, 4 Travellers and bikes.',
    );
    expect(box(['kept', 'kept', 'kept', 'kept'])).toContain(
      'Will rebuild: none; steps 1, 2, 3 and 4 are kept.',
    );
  });

  it('writes one pricing version in the singular', () => {
    expect(box(['kept', 'rebuilt', 'rebuilt', 'rebuilt'], 1)).toContain(
      'v1 and its 1 pricing version stay as they are.',
    );
  });
});

describe('the measured sentence', () => {
  it('sums the rebuilt steps in minutes, rounded, at least 1', () => {
    expect(
      measuredSentence(plan(['kept', 'rebuilt', 'rebuilt', 'rebuilt'], [100, 120, 200, 220])),
    ).toBe('Last build of this size: about 9 min.');
    expect(measuredSentence(plan(['rebuilt', 'kept', 'kept', 'kept'], [5]))).toBe(
      'Last build of this size: about 1 min.',
    );
  });

  it('is absent when a rebuilt step has no measure or nothing is rebuilt', () => {
    expect(
      measuredSentence(plan(['kept', 'rebuilt', 'rebuilt', 'kept'], [null, 60, null])),
    ).toBeNull();
    expect(measuredSentence(plan(['kept', 'kept', 'kept', 'kept']))).toBeNull();
  });
});

describe('rules', () => {
  it('writes a passed rule as its text and a failed one with both values', () => {
    const failed = rule(
      'min_trip_distance_above_grouping',
      false,
      { name: 'minimum trip distance', value: 500, unit: 'm' },
      { name: 'grouping distance', value: 600, unit: 'm' },
    );
    expect(ruleLine(failed)).toBe(
      'Minimum trip distance is greater than the grouping distance: now 500 m against 600 m',
    );
    expect(ruleLine({ ...failed, passed: true })).toBe(
      'Minimum trip distance is greater than the grouping distance',
    );
    expect(ruleFields(failed)).toEqual(['min_od_distance_m', 'clustering_threshold_m']);
  });

  it('writes the units of every kind of value', () => {
    const line = (id: string, a: RuleResult['values'][0], b: RuleResult['values'][1]) =>
      ruleLine(rule(id, false, a, b));
    expect(
      line(
        'radius_1_to_5_km',
        { name: 'radius', value: 6000, unit: 'm' },
        { name: 'allowed range', value: '1 to 5 km', unit: null },
      ),
    ).toBe('Radius between 1 and 5 km: now 6.0 km against 1 to 5 km');
    expect(
      line(
        'bikes_0_to_100_pct',
        { name: 'lowest bikes', value: -0.2, unit: 'share of docks' },
        { name: 'highest bikes', value: 1.5, unit: 'share of docks' },
      ),
    ).toBe('Bikes at 08:00: between 0 and 100 % of docks: now -20 % against 150 %');
    expect(
      line(
        'travellers_lowest_not_above_highest',
        { name: 'lowest travellers', value: 80, unit: 'travellers' },
        { name: 'highest travellers', value: 70, unit: 'travellers' },
      ),
    ).toBe(
      'Travellers per hub pair: lowest is not above highest: now 80 travellers against 70 travellers',
    );
    expect(
      line(
        'docks_at_least_1',
        { name: 'docks', value: 0, unit: 'docks' },
        { name: 'minimum', value: 1, unit: 'docks' },
      ),
    ).toBe('Docks per station: at least 1: now 0 docks against 1 docks');
    expect(
      line(
        'bikes_and_parking_lowest_not_above_highest',
        { name: 'lowest parking time', value: 6, unit: 'min' },
        { name: 'highest parking time', value: 5, unit: 'min' },
      ),
    ).toBe(
      'Bikes at 08:00 and car parking search: lowest is not above highest: now 6 min against 5 min',
    );
    expect(
      line(
        'grouping_above_0_margin_0_or_more',
        { name: 'grouping distance', value: 0, unit: 'package units' },
        { name: 'margin', value: -1, unit: 'package units' },
      ),
    ).toBe('Grouping distance above 0; outline margin 0 or more: now 0 against -1');
    expect(
      line(
        'centre_inside_area',
        { name: 'centre', value: '47, 6', unit: null },
        { name: 'available area', value: 'Geneva', unit: null },
      ),
    ).toBe('The centre is inside the area of the Geneva data: now 47, 6 against Geneva');
  });

  it('names the parking fields when the parking pair is the failing one', () => {
    const parking = rule(
      'bikes_and_parking_lowest_not_above_highest',
      false,
      { name: 'lowest parking time', value: 6, unit: 'min' },
      { name: 'highest parking time', value: 5, unit: 'min' },
    );
    expect(ruleFields(parking)).toEqual(['min_park_time_min', 'max_park_time_min']);
    expect(
      ruleFields({
        ...parking,
        values: [
          { name: 'lowest bikes', value: 1, unit: 'share of docks' },
          { name: 'highest bikes', value: 0, unit: 'share of docks' },
        ],
      }),
    ).toEqual(['min_inventory_pct', 'max_inventory_pct']);
    expect(
      ruleFields(
        rule('routing_date_inside_timetable', false, parking.values[0], parking.values[1]),
      ),
    ).toEqual([]);
  });

  it('writes the routing-date line with its dates', () => {
    const period = { routingDate: '2025-03-10' } as Parameters<typeof routingDateLine>[1];
    const timetable = { from: '2024-12-15', to: '2025-12-13' };
    expect(routingDateLine(undefined, period, timetable)).toEqual({
      passed: true,
      text: 'Routing date inside the timetable: Monday 10 March 2025 is within 15 Dec 2024 – 13 Dec 2025',
    });
    expect(
      routingDateLine(
        rule(
          'routing_date_inside_timetable',
          false,
          { name: 'a', value: 'x', unit: null },
          { name: 'b', value: 'y', unit: null },
        ),
        period,
        timetable,
      ),
    ).toEqual({
      passed: false,
      text: 'Routing date inside the timetable: now Monday 10 March 2025 against 15 Dec 2024 – 13 Dec 2025',
    });
  });
});

describe('values, changes and causes', () => {
  it('writes values with their units and reads typed ones back', () => {
    expect(valueText('radius_m', 6000)).toBe('6.0 km');
    expect(valueText('clustering_threshold_m', 400)).toBe('400 m');
    expect(valueText('max_inventory_pct', 1)).toBe('100 %');
    expect(valueText('min_park_time_min', 1)).toBe('1 min');
    expect(valueText('seed', 42)).toBe('42');
    expect(inputText('radius_m', 3000)).toBe('3.0');
    expect(inputText('max_inventory_pct', 0.35)).toBe('35');
    expect(parseInput('radius_m', '3.1')).toBe(3100);
    expect(parseInput('max_inventory_pct', '35')).toBe(0.35);
    expect(parseInput('seed', ' 7 ')).toBe(7);
    expect(parseInput('seed', '')).toBeNull();
    expect(parseInput('seed', 'x')).toBeNull();
  });

  it('writes a row per change', () => {
    expect(changeRows([{ parameter: 'clustering_threshold_m', before: 500, after: 400 }])).toEqual([
      { name: 'Grouping distance', before: '500 m', after: '400 m' },
    ]);
  });

  it('writes a sentence per non-parameter cause', () => {
    const caused: BuildPlan = {
      steps: [
        { ...step(1, 'rebuilt'), causes: [{ kind: 'package', parameters: [] }] },
        {
          ...step(2, 'rebuilt'),
          causes: [
            { kind: 'city_data', parameters: [] },
            { kind: 'package', parameters: [] },
          ],
        },
        { ...step(3, 'rebuilt'), causes: [{ kind: 'trip_planner_graph', parameters: [] }] },
        step(4, 'rebuilt'),
      ],
      verdict: { allowed: true, reasons: [] },
    };
    expect(causeRows(caused, 1, '2026-11-10T09:30:00Z')).toEqual([
      "The pricing model's package changed since v1: every step is rebuilt.",
      "The trip planner's graph changed since v1: Routes and the steps after it are rebuilt.",
      'New city data (bike stations fetched 10 Nov 2026): every step is rebuilt.',
    ]);
    expect(
      causeRows(plan(['rebuilt', 'rebuilt', 'rebuilt', 'rebuilt']), 1, '2026-11-10T09:30:00Z'),
    ).toEqual([]);
  });
});

describe('banners and the primary', () => {
  const blocked = (
    components: ('runner' | 'tripPlanner' | 'cityData' | 'package' | 'solver')[],
  ): BuildPlan => ({
    steps: plan(['rebuilt', 'rebuilt', 'rebuilt', 'rebuilt']).steps,
    verdict: {
      allowed: false,
      reasons: components.map((component) => ({ component, reason: `${component} is down` })),
    },
  });
  const ok: RuleResult = rule(
    'seed_whole_number',
    true,
    { name: 's', value: 1, unit: null },
    { name: 'a', value: 'x', unit: null },
  );
  const broken = { ...ok, passed: false };

  it('writes one sentence per reason', () => {
    expect(bannerSentences(blocked(['runner', 'tripPlanner', 'cityData', 'package']))).toEqual([
      'New builds are off: the runner is not running. Queued runs wait.',
      'This change rebuilds the routes, and the trip planner is not reachable. A change to the travellers and bikes only can still be built.',
      "No city data is imported yet. A city instance needs a timetable and bike stations; the maintainer imports Geneva's with one command (demo/README.md).",
      "New builds are off: the pricing model's package does not load on this machine.",
    ]);
    expect(Object.keys(BANNER_TEXTS)).toHaveLength(4);
    expect(bannerSentences(blocked(['solver']))).toEqual(['New builds are off: solver is down']);
  });

  it('disables the primary for a broken rule, then nothing differing, then a banner', () => {
    const input = {
      rules: [ok],
      edit: true,
      basedNumber: 1,
      plan: plan(['kept', 'kept', 'kept', 'kept']),
      changes: [],
    };
    expect(primaryState(input)).toEqual({ disabled: true, note: 'Nothing differs from v1 yet.' });
    expect(primaryState({ ...input, rules: [broken] })).toEqual({
      disabled: true,
      note: 'One rule is not met.',
    });
    expect(primaryState({ ...input, edit: false })).toEqual({ disabled: false, note: null });
    expect(
      primaryState({
        ...input,
        plan: blocked(['runner']),
        changes: [{ parameter: 'seed', before: 1, after: 2 }],
      }),
    ).toEqual({
      disabled: true,
      note: 'New builds are off: the runner is not running. Queued runs wait.',
    });
    expect(
      primaryState({
        ...input,
        plan: plan(['kept', 'rebuilt', 'rebuilt', 'rebuilt']),
        changes: [{ parameter: 'seed', before: 1, after: 2 }],
      }),
    ).toEqual({ disabled: false, note: null });
  });

  it('counts a package change as a difference', () => {
    const packaged: BuildPlan = {
      steps: plan(['rebuilt', 'rebuilt', 'rebuilt', 'rebuilt']).steps.map((item) => ({
        ...item,
        causes: [{ kind: 'package', parameters: [] }],
      })),
      verdict: { allowed: true, reasons: [] },
    };
    expect(
      primaryState({ rules: [], edit: true, basedNumber: 1, plan: packaged, changes: [] }).disabled,
    ).toBe(false);
  });
});
