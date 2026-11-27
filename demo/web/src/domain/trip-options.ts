/** L-5's option cards: the make-up sentences, the leg strip, the other bike options, the notes and
 * the no-price messages. Every number is the API's; this module only formats and selects. */
import { formatMinutes, optionName } from './hub-pair-table';
import { priceText, type QuotedMode, type QuotedOption, type TripQuote } from './traveller';
import type { RouteLegResult } from './pricing-result';

export const SET_BY_THE_PRICING_MODEL = 'SET BY THE PRICING MODEL';

export const TRAVELLER_NOTES: readonly string[] = [
  "The bike price is the pricing model's price for this option, per bike ride, added to the public transport fare. Durations and legs: trip planner, between the two hubs.",
  'The pricing model prices a shared bike only together with a public transport trip: a trip by shared bike alone has no option here.',
  'Durations and legs are those of the hub pair: the walk from your point to the hub is not included.',
];

export const NO_CAR_ROUTE =
  "No car route: the trip planner's car query failed for this hub pair when the instance was built.";

export const noBikeOption = (letter: string): string =>
  `No bike option offered: the pricing model offers none on this hub pair in Version ${letter}.`;

export const LEG_COLOURS = {
  walk: '#5a6459',
  pt: '#2a78d6',
  bike: '#008300',
  car: '#eb6834',
} as const;

export const MODE_EDGE_COLOURS: Readonly<Record<QuotedMode, string>> = {
  car: '#eb6834',
  pt_bike: '#1baf7a',
  pt_only: '#2a78d6',
};

const hasHubs = (quote: TripQuote) => quote.originHub !== null && quote.destinationHub !== null;

/** "Priced between hub H4 (Plainpalais) and hub H18 (Eaux-Vives)"; null unless a price is shown. */
export function quoteHeading(quote: TripQuote): string | null {
  if (quote.status !== 'priced' && quote.status !== 'no_bike_option') return null;
  const { originHub: from, destinationHub: to } = quote;
  if (from === null || to === null) return null;
  return `Priced between hub ${from.hubId} (${from.hubName}) and hub ${to.hubId} (${to.hubName})`;
}

/** "12 min · 1 transfer". */
export function durationLine(option: QuotedOption): string {
  const transfers = option.transfers === 1 ? '1 transfer' : `${String(option.transfers)} transfers`;
  return `${formatMinutes(option.durationS)} · ${transfers}`;
}

export interface StripSegment {
  readonly kind: keyof typeof LEG_COLOURS;
  /** Share of the strip, 0 to 1; the shares sum to 1. */
  readonly share: number;
  readonly colour: string;
}

function legKind(leg: RouteLegResult): StripSegment['kind'] {
  if (leg.mode === 'WALK' || leg.mode === 'FOOT') return 'walk';
  if (leg.mode === 'BICYCLE') return 'bike';
  if (leg.mode === 'CAR') return 'car';
  return 'pt';
}

export function legStrip(legs: readonly RouteLegResult[]): StripSegment[] {
  const total = legs.reduce((sum, leg) => sum + leg.durationS, 0);
  return legs.map((leg) => {
    const kind = legKind(leg);
    return {
      kind,
      share: total > 0 ? leg.durationS / total : 1 / legs.length,
      colour: LEG_COLOURS[kind],
    };
  });
}

export interface MakeUp {
  /** The sentence in order; the part marked `bold` is the bike price. */
  readonly parts: readonly { readonly text: string; readonly bold: boolean }[];
  readonly tag: typeof SET_BY_THE_PRICING_MODEL | null;
}

const amount = (value: number | null): string => (value ?? 0).toFixed(2);
const plain = (text: string) => ({ text, bold: false });

export function makeUp(option: QuotedOption): MakeUp {
  if (option.mode === 'car') {
    return {
      parts: [
        plain(`Car cost ${amount(option.carCost)} + parking fee ${amount(option.carParkingFee)}`),
      ],
      tag: null,
    };
  }
  if (option.mode === 'pt_only')
    return { parts: [plain(`Fare ${amount(option.ptFare)}`)], tag: null };
  const price = { text: amount(option.bikePrice), bold: true };
  const lead = `Fare ${amount(option.ptFare)} + `;
  const parts =
    option.bikeLegs >= 2
      ? [plain(`${lead}${String(option.bikeLegs)} bike rides × `), price]
      : [plain(`${lead}bike ride `), price];
  return { parts, tag: SET_BY_THE_PRICING_MODEL };
}

/** The offered PT + bike options besides the most taken one: flow highest first, then arc id. */
export function otherBikeOptions(quote: TripQuote): QuotedOption[] {
  return quote.options
    .filter((option) => option.mode === 'pt_bike' && !option.mostTaken)
    .sort(
      (a, b) =>
        (b.flow ?? 0) - (a.flow ?? 0) ||
        a.arcId.localeCompare(b.arcId, undefined, { numeric: true }),
    );
}

export const otherBikeOptionsLabel = (n: number): string =>
  `+ ${String(n)} other bike options offered`;

export function otherBikeOptionLine(option: QuotedOption): {
  legs: string;
  duration: string;
  price: string;
} {
  return {
    legs: optionName(option.legs),
    duration: formatMinutes(option.durationS),
    price: priceText(option.price),
  };
}

export const radiusKm = (radiusM: number): string => String(Number((radiusM / 1000).toFixed(3)));

/** The message(s) of a status with no price; `outside_zone` has one line per point outside. */
export function noPriceMessages(
  quote: TripQuote,
  instanceVersionName: string,
  radiusM: number | null,
): string[] {
  const from = quote.originHub?.hubId ?? '';
  const to = quote.destinationHub?.hubId ?? '';
  switch (quote.status) {
    case 'same_hub':
      return hasHubs(quote)
        ? [
            `No model price for this trip: both points are in hub ${from}. The model prices trips between hubs.`,
          ]
        : [];
    case 'under_minimum_distance':
      return [
        `No model price: hubs ${from} and ${to} are closer than this instance's minimum trip distance (${String(quote.minTripDistanceM ?? 0)} m).`,
      ];
    case 'removed_by_quality_check':
      return [
        `No model price: the routes of ${from} → ${to} were removed when the instance's routes were checked.`,
      ];
    case 'no_route':
      return [
        `No model price: the trip planner found no public transport route for ${from} → ${to} when the instance was built.`,
      ];
    case 'outside_zone': {
      if (radiusM === null) return [];
      const lines: string[] = [];
      if (quote.fromPoint?.status === 'outside_zone') lines.push('A');
      if (quote.toPoint?.status === 'outside_zone') lines.push('B');
      return lines.map(
        (point) =>
          `Point ${point} is outside the ${radiusKm(radiusM)} km zone of ${instanceVersionName}.`,
      );
    }
    default:
      return [];
  }
}
