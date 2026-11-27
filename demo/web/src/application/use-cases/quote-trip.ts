import type { GeoPoint } from '../../domain/map';
import {
  finishedVersionChoices,
  type PlaceLine,
  type TripQuote,
  type VersionChoice,
} from '../../domain/traveller';
import type { PricingVersion } from '../../domain/pricing-version';
import type { CityInstanceGateway } from '../ports/city-instance-gateway';
import type { PricingGateway } from '../ports/pricing-gateway';
import type { TripGateway } from '../ports/trip-gateway';

/** The trip between two points for one pricing version; none is asked for until a point is set. */
export function quoteTrip(
  { trips }: { trips: TripGateway },
  pricingVersionId: string,
  period: string | null,
  from: GeoPoint | null,
  to: GeoPoint | null,
): Promise<TripQuote | null> {
  if (from === null && to === null) return Promise.resolve(null);
  return trips.quote(pricingVersionId, period, from, to);
}

/** The place names that match what is typed; nothing before two characters. */
export function searchPlaces(
  { trips }: { trips: TripGateway },
  instanceVersionId: string,
  text: string,
): Promise<PlaceLine[]> {
  const wanted = text.trim();
  if (wanted.length < 2) return Promise.resolve([]);
  return trips.placeNames(instanceVersionId, wanted);
}

/** Every finished pricing version of every built instance version, in the menu's order. */
export async function loadTravellerChoices(gateways: {
  cityInstances: CityInstanceGateway;
  pricing: PricingGateway;
}): Promise<VersionChoice[]> {
  const menu = await gateways.cityInstances.menu();
  const built = menu.flatMap((entry) =>
    entry.versions.filter(
      (version) => version.state === 'ready' && version.pricingVersionCount > 0,
    ),
  );
  const lists = await Promise.all(built.map((version) => gateways.pricing.list(version.id)));
  const byInstanceVersion: Record<string, readonly PricingVersion[]> = {};
  built.forEach((version, at) => {
    byInstanceVersion[version.id] = lists[at] ?? [];
  });
  return finishedVersionChoices(menu, byInstanceVersion);
}
