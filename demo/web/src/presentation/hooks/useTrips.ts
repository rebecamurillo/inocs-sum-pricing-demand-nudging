import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import {
  loadTravellerChoices,
  quoteTrip,
  searchPlaces,
} from '../../application/use-cases/quote-trip';
import type { GeoPoint } from '../../domain/map';
import { useGateways } from './gateways';

export const TRAVELLER_CHOICES_KEY = ['traveller-choices'] as const;
/** The wait after the last key before the names are asked for. */
export const PLACE_NAMES_DEBOUNCE_MS = 250;

/** Every finished pricing version of every built instance version, for row 1. */
export function useTravellerChoices() {
  const { cityInstances, pricing } = useGateways();
  return useQuery({
    queryKey: TRAVELLER_CHOICES_KEY,
    queryFn: () => loadTravellerChoices({ cityInstances, pricing }),
    retry: false,
  });
}

/** The value, once it has stayed the same for `ms`. */
function useDebounced<T>(value: T, ms: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => {
      setSettled(value);
    }, ms);
    return () => {
      clearTimeout(timer);
    };
  }, [value, ms]);
  return settled;
}

/** The names that match `text`, asked for 250 ms after the last key and from two characters. */
export function usePlaceNames(instanceVersionId: string, text: string) {
  const { trips } = useGateways();
  const wanted = text.trim();
  const settled = useDebounced(wanted, PLACE_NAMES_DEBOUNCE_MS);
  const query = useQuery({
    queryKey: ['place-names', instanceVersionId, settled],
    queryFn: () => searchPlaces({ trips }, instanceVersionId, settled),
    enabled: settled.length >= 2,
    retry: false,
  });
  // Names of an earlier text are not the names of this one while the typing has not settled.
  return { ...query, data: settled === wanted ? query.data : undefined };
}

const pointKey = (point: GeoPoint | null) =>
  point === null ? '-' : `${String(point.lat)},${String(point.lon)}`;

/** The key of the points and the period a quote was asked for. */
export const tripKey = (period: string | null, a: GeoPoint | null, b: GeoPoint | null) =>
  `${period ?? '-'}|${pointKey(a)}|${pointKey(b)}`;

/**
 * The quote of the points set for a version; it keeps the previous answer while the next one is
 * read (`isPlaceholderData`), so the cards can show the old price struck through.
 */
export function useTripQuote(
  pricingVersionId: string,
  period: string | null,
  a: GeoPoint | null,
  b: GeoPoint | null,
) {
  const { trips } = useGateways();
  return useQuery({
    queryKey: ['trip-quote', pricingVersionId, tripKey(period, a, b)],
    queryFn: () => quoteTrip({ trips }, pricingVersionId, period, a, b),
    enabled: a !== null || b !== null,
    placeholderData: keepPreviousData,
    retry: false,
  });
}
