import { describe, expect, it, vi } from 'vitest';
import { ApiProblemError } from '../../application/errors';
import { HttpTripGateway } from './http-trip-gateway';

function answering(status: number, body: unknown) {
  return vi.fn<typeof fetch>(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
}

const number = (value: number) => ({ value, unit: 'chf', source: 'derived', group: 'headline' });

describe('HttpTripGateway', () => {
  it('asks for the names of an instance version and maps the lines', async () => {
    const fetchImpl = answering(200, {
      items: [{ name: 'Plainpalais', kind: 'stop', hub_id: 'H4', lat: 46.2, lon: 6.14 }],
    });

    const lines = await new HttpTripGateway(fetchImpl).placeNames('geneva-3km.v1', 'plain pal');

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(
      '/api/v1/place-names?instance_version=geneva-3km.v1&q=plain+pal',
    );
    expect(lines).toEqual([
      { name: 'Plainpalais', kind: 'stop', hubId: 'H4', lat: 46.2, lon: 6.14 },
    ]);
  });

  it('asks for a quote with the points as lat,lon and maps points and options', async () => {
    const fetchImpl = answering(200, {
      status: 'priced',
      from_point: {
        status: 'matched',
        hub_id: 'H4',
        hub_name: 'Plainpalais',
        nearest_hub_id: null,
        nearest_stop_name: 'Plainpalais',
        distance_from_outline_m: null,
        distance_to_hub_centre_m: null,
      },
      to_point: {
        status: 'no_hub_here',
        hub_id: null,
        hub_name: null,
        nearest_hub_id: 'H7',
        nearest_stop_name: null,
        distance_from_outline_m: number(412),
        distance_to_hub_centre_m: null,
      },
      origin_hub: { hub_id: 'H4', hub_name: 'Plainpalais' },
      destination_hub: { hub_id: 'H18', hub_name: 'Eaux-Vives' },
      min_trip_distance_m: number(500),
      no_car_option: false,
      options: [
        {
          mode: 'car',
          most_taken: true,
          price: number(4.5),
          arc_id: 'c1',
          bike_legs: number(0),
          bike_price: null,
          pt_fare: null,
          car_cost: number(3.4),
          car_parking_fee: number(1.1),
          duration_s: number(600),
          transfers: number(0),
          flow: null,
          legs: [],
        },
        {
          mode: 'pt_bike',
          most_taken: false,
          price: number(3.8),
          arc_id: 'b1',
          bike_legs: number(1),
          bike_price: number(1.8),
          pt_fare: number(2),
          car_cost: null,
          car_parking_fee: null,
          duration_s: number(1260),
          transfers: number(1),
          flow: number(12),
          legs: [
            {
              mode: 'TRAM',
              line: '12',
              from_name: 'Plainpalais',
              to_name: 'Rive',
              duration_s: number(600),
            },
          ],
        },
      ],
    });

    const quote = await new HttpTripGateway(fetchImpl).quote(
      'geneva-3km.v1.B',
      'mon-08',
      { lat: 46.2, lon: 6.14 },
      { lat: 46.21, lon: 6.15 },
    );

    expect(fetchImpl.mock.calls[0]?.[0]).toBe(
      '/api/v1/trip-quotes?pricing_version=geneva-3km.v1.B&period=mon-08&from=46.2,6.14&to=46.21,6.15',
    );
    expect(quote.status).toBe('priced');
    expect(quote.fromPoint).toMatchObject({ status: 'matched', hubId: 'H4' });
    expect(quote.toPoint).toMatchObject({ nearestHubId: 'H7', distanceFromOutlineM: 412 });
    expect(quote.originHub).toEqual({ hubId: 'H4', hubName: 'Plainpalais' });
    expect(quote.destinationHub).toEqual({ hubId: 'H18', hubName: 'Eaux-Vives' });
    expect(quote.minTripDistanceM).toBe(500);
    expect(quote.noCarOption).toBe(false);
    expect(quote.options).toEqual([
      {
        mode: 'car',
        mostTaken: true,
        price: 4.5,
        arcId: 'c1',
        durationS: 600,
        transfers: 0,
        bikeLegs: 0,
        bikePrice: null,
        ptFare: null,
        carCost: 3.4,
        carParkingFee: 1.1,
        flow: null,
        legs: [],
      },
      {
        mode: 'pt_bike',
        mostTaken: false,
        price: 3.8,
        arcId: 'b1',
        durationS: 1260,
        transfers: 1,
        bikeLegs: 1,
        bikePrice: 1.8,
        ptFare: 2,
        carCost: null,
        carParkingFee: null,
        flow: 12,
        legs: [
          { mode: 'TRAM', line: '12', fromPlace: 'Plainpalais', toPlace: 'Rive', durationS: 600 },
        ],
      },
    ]);
  });

  it('leaves out the period and a missing point', async () => {
    const fetchImpl = answering(200, {
      status: 'one_point',
      from_point: null,
      to_point: null,
      origin_hub: null,
      destination_hub: null,
      min_trip_distance_m: null,
      no_car_option: null,
      options: [],
    });

    await new HttpTripGateway(fetchImpl).quote('v.A', null, null, { lat: 1, lon: 2 });

    expect(fetchImpl.mock.calls[0]?.[0]).toBe('/api/v1/trip-quotes?pricing_version=v.A&to=1,2');
  });

  it('raises the API problem on a 404 or a 422, and an unreachable API', async () => {
    const problem = { code: 'no_result', title: 'No result', detail: 'The version has no result.' };
    await expect(
      new HttpTripGateway(answering(404, problem)).quote('v.A', null, { lat: 1, lon: 2 }, null),
    ).rejects.toMatchObject({ code: 'no_result' });
    await expect(
      new HttpTripGateway(answering(422, { nothing: true })).placeNames('v', 'ab'),
    ).rejects.toMatchObject({ code: 'unexpected_response' });
    const down = vi.fn<typeof fetch>(() => Promise.reject(new Error('offline')));
    await expect(new HttpTripGateway(down).placeNames('v', 'ab')).rejects.toBeInstanceOf(
      ApiProblemError,
    );
  });
});
