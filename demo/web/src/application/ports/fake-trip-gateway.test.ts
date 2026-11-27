import { describe, expect, it } from 'vitest';
import { fakeTrips } from './fake-trip-gateway';

describe('fakeTrips', () => {
  it('lists the places that match two characters or more, and records the call', async () => {
    const { gateway, placeCalls } = fakeTrips();
    expect(await gateway.placeNames('geneva-3km.v1', 'P')).toEqual([]);
    expect((await gateway.placeNames('geneva-3km.v1', 'plain')).map((line) => line.kind)).toEqual([
      'stop',
      'bike_station',
    ]);
    expect(placeCalls).toHaveLength(2);
  });

  it('prices two matched points per version and reads one point as one point', async () => {
    const { gateway, quoteCalls } = fakeTrips();
    const a = { lat: 46.199, lon: 6.14 };
    const b = { lat: 46.2102, lon: 6.1424 };
    const priced = await gateway.quote('geneva-3km.v1.B', null, a, b);
    expect(priced.status).toBe('priced');
    expect(priced.fromPoint?.hubId).toBe('H4');
    const other = await gateway.quote('geneva-3km.v1.C', null, a, b);
    expect(other.options.find((o) => o.mode === 'pt_bike' && o.mostTaken)?.price).not.toBe(
      priced.options.find((o) => o.mode === 'pt_bike' && o.mostTaken)?.price,
    );
    expect((await gateway.quote('geneva-3km.v1.B', null, a, null)).status).toBe('one_point');
    expect(
      (await gateway.quote('geneva-3km.v1.B', null, { lat: 0, lon: 0 }, b)).fromPoint?.status,
    ).toBe('no_hub_here');
    expect(quoteCalls).toHaveLength(4);
  });

  it('answers a same-hub status for two points in one hub, and a configured answer', async () => {
    const { gateway, answer } = fakeTrips();
    const a = { lat: 46.199, lon: 6.14 };
    const b = { lat: 46.2102, lon: 6.1424 };
    const same = await gateway.quote('geneva-3km.v1.B', null, a, a);
    expect(same.status).toBe('same_hub');
    expect(same.originHub).toEqual({ hubId: 'H4', hubName: 'Plainpalais' });
    expect(same.options).toEqual([]);
    answer({ status: 'no_route' });
    expect((await gateway.quote('geneva-3km.v1.B', null, a, b)).status).toBe('no_route');
    answer(null);
    expect((await gateway.quote('geneva-3km.v1.B', null, a, b)).status).toBe('priced');
  });

  it('answers the stored options of a pair with each leg kind, and records the call', async () => {
    const { gateway, routeCalls, busShapes } = fakeTrips();
    const list = await gateway.routeOptions('geneva-3km.v1', 'mon-08', 'H4', 'H1');
    expect(routeCalls).toEqual([
      {
        instanceVersionId: 'geneva-3km.v1',
        period: 'mon-08',
        originHubId: 'H4',
        destinationHubId: 'H1',
      },
    ]);
    expect(list.busShapes).toBe(true);
    expect(list.items.map((item) => item.arcId).sort()).toEqual(['b1', 'b2', 'b3', 'c1', 'p1']);
    const kinds = new Set(list.items.flatMap((item) => item.legs.map((l) => l.lineKind)));
    expect(kinds).toEqual(new Set(['street_path', 'timetable_shape', 'straight_line']));
    busShapes(false);
    const noBus = await gateway.routeOptions('geneva-3km.v1', null, 'H4', 'H1');
    expect(noBus.busShapes).toBe(false);
    expect(
      noBus.items.flatMap((item) => item.legs).some((l) => l.lineKind === 'timetable_shape'),
    ).toBe(false);
  });
});
