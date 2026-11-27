import type { GeoPoint } from '../../domain/map';
import type { PlaceLine, TripQuote } from '../../domain/traveller';

export interface TripGateway {
  /** The stop and bike-station names of an instance version that match `text`, at most 10. */
  placeNames(instanceVersionId: string, text: string): Promise<PlaceLine[]>;
  /**
   * A trip quoted from stored data. `period` null leaves the version's own period to the API;
   * at least one point must be set.
   */
  quote(
    pricingVersionId: string,
    period: string | null,
    from: GeoPoint | null,
    to: GeoPoint | null,
  ): Promise<TripQuote>;
}
