import type { GeoPoint, MapHub } from './map';
import type { ResultNumber } from './pricing-result';

/** A hub pair with bike rides: a line between its two hub centres. */
export interface ShowcasePair {
  readonly originHub: string;
  readonly destinationHub: string;
  readonly origin: GeoPoint;
  readonly destination: GeoPoint;
  /** The ride-weighted mean bike price, computed from the model's flows. */
  readonly meanBikePrice: ResultNumber;
  /** The bike rides, computed from the model's flows. */
  readonly bikeRides: ResultNumber;
}

/** The result marked for the home page, with what Home draws from it (`GET /showcase`). */
export interface Showcase {
  readonly pricingVersionId: string;
  readonly periodId: string;
  readonly instanceVersionId: string;
  readonly instanceVersionName: string;
  readonly letter: string;
  readonly markedAt: string;
  readonly datasetId: string;
  readonly city: string;
  readonly radiusKm: ResultNumber;
  readonly periodLabel: string;
  /** Car trips per 100 simulated travellers with the flat price, in points. */
  readonly carShareFlat: ResultNumber;
  readonly carShareVersion: ResultNumber;
  /** `carShareFlat` minus `carShareVersion`, in points. */
  readonly carShareDifference: ResultNumber;
  readonly flatPrice: ResultNumber;
  readonly rule: { readonly id: string; readonly version: number; readonly current: boolean };
  readonly studyCircle: { readonly centre: GeoPoint; readonly radiusM: number };
  readonly hubs: readonly MapHub[];
  readonly hubPairs: readonly ShowcasePair[];
}
