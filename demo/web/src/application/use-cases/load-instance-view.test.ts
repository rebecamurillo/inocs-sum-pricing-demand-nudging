import { describe, expect, it, vi } from 'vitest';
import {
  fakeCityInstances,
  sampleDataset,
  sampleFailedRoutes,
  sampleMenu,
  sampleVersion,
} from '../ports/fake-city-instance-gateway';
import {
  loadInstanceGeometry,
  loadInstanceMenu,
  loadInstanceView,
  loadRouteFailures,
} from './load-instance-view';

describe('loadInstanceView', () => {
  it('reads the version with its instance name, pricing versions and data set', async () => {
    const view = await loadInstanceView({ cityInstances: fakeCityInstances() }, 'geneva-3km.v1');

    expect(view).toEqual({
      version: sampleVersion,
      instanceName: 'Geneva 3 km',
      dataset: sampleDataset,
      pricingVersionCount: 3,
    });
  });

  it('asks for the data set the menu names', async () => {
    const dataset = vi.fn(() => Promise.resolve(sampleDataset));

    await loadInstanceView({ cityInstances: fakeCityInstances({ dataset }) }, 'geneva-3km.v1');

    expect(dataset).toHaveBeenCalledWith('geneva-2026-11-26');
  });

  it('answers null for a version the API does not have, reading nothing more', async () => {
    const menu = vi.fn(() => Promise.resolve(sampleMenu));

    const view = await loadInstanceView({ cityInstances: fakeCityInstances({ menu }) }, 'nope.v1');

    expect(view).toBeNull();
    expect(menu).not.toHaveBeenCalled();
  });

  it('counts no pricing version for a version the menu does not list', async () => {
    const menu = () =>
      Promise.resolve([
        { id: 'geneva-3km', name: 'Geneva 3 km', datasetId: sampleDataset.id, versions: [] },
      ]);

    const view = await loadInstanceView(
      { cityInstances: fakeCityInstances({ menu }) },
      'geneva-3km.v1',
    );

    expect(view?.pricingVersionCount).toBe(0);
  });

  it('fails when the instance or its data set cannot be found', async () => {
    const noMenu = fakeCityInstances({ menu: () => Promise.resolve([]) });
    const noDataset = fakeCityInstances({ dataset: () => Promise.resolve(null) });

    await expect(loadInstanceView({ cityInstances: noMenu }, 'geneva-3km.v1')).rejects.toThrow(
      'could not be found',
    );
    await expect(loadInstanceView({ cityInstances: noDataset }, 'geneva-3km.v1')).rejects.toThrow(
      'could not be found',
    );
  });
});

describe('loadRouteFailures', () => {
  const failure = {
    originHub: 'H1',
    destinationHub: 'H2',
    query: 'car',
    kind: 'no_route',
    message: 'none',
    attempts: 1,
  } as const;

  it('reads the failures of the run that produced the routes', async () => {
    const routeFailures = vi.fn(() => Promise.resolve([failure]));

    const found = await loadRouteFailures(
      { cityInstances: fakeCityInstances({ routeFailures }) },
      sampleFailedRoutes,
    );

    expect(found).toEqual([failure]);
    expect(routeFailures).toHaveBeenCalledWith('run-1');
  });

  it('reads nothing when no query failed, the run is unknown or the version is not built', async () => {
    const routeFailures = vi.fn(() => Promise.resolve([failure]));
    const gateways = { cityInstances: fakeCityInstances({ routeFailures }) };

    expect(await loadRouteFailures(gateways, { ...sampleFailedRoutes, queriesFailed: 0 })).toEqual(
      [],
    );
    expect(await loadRouteFailures(gateways, { ...sampleFailedRoutes, runId: null })).toEqual([]);
    expect(await loadRouteFailures(gateways, null)).toEqual([]);
    expect(routeFailures).not.toHaveBeenCalled();
  });
});

describe('loadInstanceMenu and loadInstanceGeometry', () => {
  it('reads the menu', async () => {
    expect(await loadInstanceMenu({ cityInstances: fakeCityInstances() })).toEqual(sampleMenu);
  });

  it('reads the stations, hubs and hub pairs of a version together', async () => {
    const gateway = fakeCityInstances();

    const geometry = await loadInstanceGeometry({ cityInstances: gateway }, 'geneva-3km.v1');

    expect(geometry.stations.map((s) => s.id)).toEqual(['p1', 'b1']);
    expect(geometry.hubs.map((h) => h.label)).toEqual(['Hub H1', 'Hub H2']);
    expect(geometry.hubPairs).toEqual([{ originHub: 'H1', destinationHub: 'H2' }]);
  });
});
