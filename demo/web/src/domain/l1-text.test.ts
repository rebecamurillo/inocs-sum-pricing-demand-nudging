import { describe, expect, it } from 'vitest';
import type {
  DatasetInfo,
  InstanceParameters,
  InstancePeriod,
  RouteFailure,
  RoutesSummary,
} from './city-instance';
import {
  breadcrumb,
  centreText,
  collapsedCount,
  failureRowTexts,
  formatDate,
  formatInstantDay,
  groupThousands,
  l1Groups,
  latestVersion,
  menuVersionState,
  packageUnitsCaption,
  periodChip,
  radiusText,
  readyLine,
  routesLine,
  routingMomentSentence,
  showPairsLink,
  timetableSentence,
  usedBy,
  versionTag,
} from './l1-text';

const parameters: InstanceParameters = {
  centerLat: 46.2057,
  centerLon: 6.1489,
  radiusM: 3000,
  clusteringThresholdM: 500,
  clusteringBufferM: 100,
  minOdDistanceM: 900,
  minDemand: 10,
  maxDemand: 70,
  fixedCapacity: 20,
  minInventoryPct: 0,
  maxInventoryPct: 100,
  minParkTimeMin: 1,
  maxParkTimeMin: 5,
  seed: 42,
};

const period: InstancePeriod = {
  id: 'geneva-3km.v1.mon-08',
  label: 'Monday 08:00–09:00',
  startTime: '08:00:00',
  routingDate: '2025-03-10',
  routingTime: '08:30:00',
  arriveBy: true,
  provisional: true,
};

const dataset: DatasetInfo = {
  id: 'geneva-2026-11-26',
  name: 'Geneva · tpg + Donkey Republic',
  timetableValidFrom: '2024-12-15',
  timetableValidTo: '2025-12-13',
  bikeStationsFetchedAt: '2026-11-10T09:30:00Z',
};

const routes: RoutesSummary = {
  queries: 3960,
  queriesFailed: 14,
  failurePct: 0.3535,
  pairsWithoutPublicTransport: 9,
  pairsWithoutCar: 5,
  retries: 3,
  runId: 'run-1',
};

describe('numbers and dates', () => {
  it('groups thousands with a space', () => {
    expect(groupThousands(0)).toBe('0');
    expect(groupThousands(999)).toBe('999');
    expect(groupThousands(1412)).toBe('1 412');
    expect(groupThousands(72240)).toBe('72 240');
    expect(groupThousands(1234567)).toBe('1 234 567');
    expect(groupThousands(-1412)).toBe('-1 412');
  });

  it('writes a calendar date as day, short month, year', () => {
    expect(formatDate('2024-12-15')).toBe('15 Dec 2024');
    expect(formatDate('2025-09-03')).toBe('3 Sep 2025');
  });

  it('writes an instant as the calendar day in Europe/Zurich', () => {
    expect(formatInstantDay('2026-11-12T10:00:00Z')).toBe('12 Nov 2026');
    // 23:30 UTC is already the next day in Zurich (UTC+1 in winter, UTC+2 in summer).
    expect(formatInstantDay('2026-11-12T23:30:00Z')).toBe('13 Nov 2026');
    expect(formatInstantDay('2026-06-30T22:30:00Z')).toBe('1 Jul 2026');
  });
});

describe('the ready line', () => {
  it('uses the singular for one pricing version', () => {
    expect(usedBy(1)).toBe('used by 1 pricing version');
    expect(usedBy(0)).toBe('used by 0 pricing versions');
    expect(usedBy(3)).toBe('used by 3 pricing versions');
  });

  it('names the day it was saved', () => {
    expect(readyLine(new Date('2026-11-12T10:00:00Z'), 0)).toBe(
      'Ready · saved 12 Nov 2026 · used by 0 pricing versions',
    );
    expect(readyLine(new Date('2026-11-12T10:00:00Z'), 1)).toBe(
      'Ready · saved 12 Nov 2026 · used by 1 pricing version',
    );
  });
});

describe('a version without a save instant or periods', () => {
  it('leaves the save day out of the ready line', () => {
    expect(readyLine(null, 0)).toBe('Ready · used by 0 pricing versions');
  });

  it('writes the groups with no routing sentence and the default start hour', () => {
    const flat = l1Groups({ parameters, periods: [] }, dataset).flatMap((group) => group.fields);

    expect(flat.find((f) => f.name === 'Periods prepared')).toMatchObject({
      value: '',
      sentence:
        'The periods this instance has routes and travellers for; a pricing version chooses among them. 0 in this version.',
    });
    expect(flat.map((f) => f.name)).toContain('Bikes at 08:00');
  });
});

describe('the parameter texts', () => {
  it('writes the timetable sentence', () => {
    expect(timetableSentence('2024-12-15', '2025-12-13', '2026-11-10T09:30:00Z')).toBe(
      'Timetable valid 15 Dec 2024 to 13 Dec 2025 · bike stations fetched 10 Nov 2026.',
    );
  });

  it('writes the centre with four decimals and the radius with one', () => {
    expect(centreText(46.2057, 6.1489)).toBe('46.2057, 6.1489');
    expect(centreText(46.2, 6.15)).toBe('46.2000, 6.1500');
    expect(radiusText(3000)).toBe('3.0 km');
    expect(radiusText(1500)).toBe('1.5 km');
  });

  it('writes the package units caption', () => {
    expect(packageUnitsCaption(500, 46.2057)).toBe(
      'package units, about 0.69 m on the ground at Geneva: 500 is about 346 m',
    );
    expect(packageUnitsCaption(100, 46.2057)).toBe(
      'package units, about 0.69 m on the ground at Geneva: 100 is about 69 m',
    );
  });

  it('writes the routing moment, with "provisional" only when it is', () => {
    expect(routingMomentSentence(period)).toBe(
      'Routes planned for Monday 10 March 2025, arrive by 08:30 · provisional.',
    );
    expect(routingMomentSentence({ ...period, arriveBy: false, provisional: false })).toBe(
      'Routes planned for Monday 10 March 2025, leave at 08:30.',
    );
  });
});

describe('the routes line', () => {
  it('writes the failed form with one decimal', () => {
    expect(routesLine({ ...routes, failurePct: 0.3535 })).toBe(
      'Routes: 14 of 3 960 trip-planner queries gave no route (0.4 %). 9 hub pairs have no public transport route and are not priced; 5 have no car option. A technical error is tried 3 times before it counts.',
    );
  });

  it('uses the recorded retries', () => {
    expect(routesLine({ ...routes, retries: 5 })).toContain('is tried 5 times');
  });

  it('uses the singular for a count of 1 and the plural for 0', () => {
    expect(
      routesLine({
        ...routes,
        queriesFailed: 2,
        pairsWithoutPublicTransport: 1,
        pairsWithoutCar: 1,
      }),
    ).toContain('1 hub pair has no public transport route and is not priced; 1 has no car option.');
    expect(
      routesLine({
        ...routes,
        queriesFailed: 2,
        pairsWithoutPublicTransport: 0,
        pairsWithoutCar: 2,
      }),
    ).toContain(
      '0 hub pairs have no public transport route and are not priced; 2 have no car option.',
    );
  });

  it('writes the form with no failure', () => {
    expect(routesLine({ ...routes, queries: 48, queriesFailed: 0, failurePct: 0 })).toBe(
      'Routes: all 48 trip-planner queries gave a route.',
    );
  });

  it('writes the link with the singular for 1', () => {
    expect(showPairsLink(14)).toBe('Show the 14 hub pairs without a route');
    expect(showPairsLink(1)).toBe('Show the 1 hub pair without a route');
  });
});

describe('a failure row', () => {
  const label = (id: string) => `Hub ${id}`;
  const base: RouteFailure = {
    originHub: 'H1',
    destinationHub: 'H2',
    query: 'pt_bike',
    kind: 'no_route',
    message: 'none',
    attempts: 1,
  };

  it('reads a public transport query that found no route', () => {
    expect(failureRowTexts(base, 3, label)).toEqual({
      fromTo: 'Hub H1 → Hub H2',
      query: 'Public transport',
      whatHappened: 'No route found',
      effect: 'Not in the instance: not priced',
    });
  });

  it('reads a car query that ended in a technical error after the recorded retries', () => {
    expect(
      failureRowTexts({ ...base, query: 'car', kind: 'technical', message: 'timeout' }, 3, label),
    ).toEqual({
      fromTo: 'Hub H1 → Hub H2',
      query: 'Car',
      whatHappened: 'Trip planner error after 3 tries: timeout',
      effect: 'No car option',
    });
  });
});

describe('the menu and the top bar', () => {
  it('writes the breadcrumb, the chip, the tag and the counts', () => {
    expect(breadcrumb('Geneva 3 km', 1)).toBe('Geneva 3 km v1 › Instance set-up');
    expect(periodChip('Monday 08:00–09:00')).toBe('Period Monday 08:00–09:00');
    expect(versionTag(2)).toBe('v2');
    expect(collapsedCount(1)).toBe('1 version');
    expect(collapsedCount(3)).toBe('3 versions');
  });

  it('writes a state as the API does', () => {
    expect(menuVersionState('ready')).toBe('ready');
    expect(menuVersionState('building')).toBe('● building');
  });

  it('writes the other run states of a menu row', () => {
    expect(menuVersionState('queued', 2)).toBe('◷ queued · 2nd');
    expect(menuVersionState('queued')).toBe('◷ queued');
    expect(menuVersionState('failed')).toBe('✕ failed');
    expect(menuVersionState('cancelled')).toBe('cancelled');
    expect(menuVersionState('draft')).toBe('draft');
  });

  it('finds the latest version of an entry', () => {
    const version = (number: number) => ({
      id: `x.v${String(number)}`,
      number,
      status: 'sealed' as const,
      state: 'ready',
      pricingVersionCount: 0,
    });
    const entry = { id: 'x', name: 'X', datasetId: 'd', versions: [version(1), version(3)] };

    expect(latestVersion(entry)?.number).toBe(3);
    expect(latestVersion({ ...entry, versions: [] })).toBeNull();
  });
});

describe('the four groups', () => {
  const groups = l1Groups({ parameters, periods: [period] }, dataset);
  const flat = groups.flatMap((group) => group.fields.map((f) => ({ group: group.name, ...f })));

  it('names the groups in order', () => {
    expect(groups.map((group) => [group.number, group.name])).toEqual([
      [1, 'Area'],
      [2, 'Hubs'],
      [3, 'Routes'],
      [4, 'Travellers and bikes'],
    ]);
  });

  it('writes every field with its value, sentence and package names', () => {
    expect(flat.map((f) => [f.name, f.value, f.packageNames])).toEqual([
      ['City data', 'Geneva · tpg + Donkey Republic', 'gtfs_path · gbfs_path'],
      ['Centre', '46.2057, 6.1489', 'center_lat · center_lon'],
      ['Radius', '3.0 km', 'radius_m'],
      ['Grouping distance', '500 m', 'clustering_threshold_m'],
      ['Hub outline margin', '100 m', 'clustering_buffer_m'],
      ['Minimum trip distance', '900 m', 'min_od_distance_m'],
      ['Periods prepared', 'Monday 08:00–09:00', 'otp_timestamp'],
      ['Travellers per hub pair', '10 to 70', 'min_demand · max_demand'],
      ['Docks per station', '20', 'fixed_capacity'],
      ['Bikes at 08:00', '0 to 100 % of docks', 'min_inventory_pct · max_inventory_pct'],
      ['Car parking search', '1 to 5 min', 'min_park_time_min · max_park_time_min'],
      ['Random seed', '42', 'seed'],
    ]);
    expect(flat.map((f) => f.sentence)).toEqual([
      'Public transport timetable (GTFS) and shared-bike stations (GBFS), preloaded for Geneva. Timetable valid 15 Dec 2024 to 13 Dec 2025 · bike stations fetched 10 Nov 2026.',
      null,
      'From 1 to 5 km. A larger zone has more hubs and takes longer to build.',
      'Stops and stations closer than this form one hub.',
      "Space drawn around a hub's stops and stations.",
      'Hub pairs closer than this are not priced. Must be greater than the grouping distance.',
      'The periods this instance has routes and travellers for; a pricing version chooses among them. One in this version. Routes planned for Monday 10 March 2025, arrive by 08:30 · provisional.',
      'Drawn at random for the period.',
      'Places for bikes at each station.',
      'Drawn at random for each station.',
      'Time added to a car trip, drawn at random.',
      'The same seed draws the same travellers and bikes.',
    ]);
  });

  it('adds the package units caption to the two hub distances only', () => {
    expect(flat.filter((f) => f.caption !== null).map((f) => [f.name, f.caption])).toEqual([
      [
        'Grouping distance',
        'package units, about 0.69 m on the ground at Geneva: 500 is about 346 m',
      ],
      [
        'Hub outline margin',
        'package units, about 0.69 m on the ground at Geneva: 100 is about 69 m',
      ],
    ]);
  });

  it('counts the periods when there are several', () => {
    const two = l1Groups(
      { parameters, periods: [period, { ...period, label: 'Monday 17:00–18:00' }] },
      dataset,
    );
    const periods = two[2]?.fields[1];

    expect(periods?.value).toBe('Monday 08:00–09:00, Monday 17:00–18:00');
    expect(periods?.sentence).toContain('2 in this version.');
  });
});
