import { useId, useMemo, useRef, useState, type KeyboardEvent } from 'react';
import { circleBounds, type GeoBounds, type GeoPoint } from '../../domain/map';
import { travellerRoute, type LabRoute } from '../../domain/route';
import {
  DAY_NAME,
  NEXT_VERSION_TAG,
  NEXT_VERSION_TEXT,
  OPTION_CARDS,
  ROW_TITLES,
  SWAP_LABEL,
  TRAVELLER_BRIEF,
  TRIP_SENTENCE,
  cardPrices,
  fieldForClick,
  instanceSentence,
  nextPrevious,
  noHubMessage,
  placeLine,
  pointFieldText,
  scopeLine,
  timeSlots,
  type PlaceLine,
  type PointField,
  type QuotedMode,
  type ShownQuote,
  type VersionChoice,
} from '../../domain/traveller';
import {
  NO_CAR_ROUTE,
  TRAVELLER_NOTES,
  noBikeOption,
  noPriceMessages,
  otherBikeOptions,
  quoteHeading,
} from '../../domain/trip-options';
import {
  ROUTE_STYLES,
  defaultCard,
  routeBounds,
  routeLegendKinds,
  straightLegsSentence,
} from '../../domain/trip-route';
import { OptionCard } from './OptionCard';
import { useInstanceGeometry, useInstanceView } from '../hooks/useCityInstances';
import { tripKey, usePlaceNames, useRouteOptions, useTripQuote } from '../hooks/useTrips';
import {
  useMapClick,
  useMapFit,
  useMapLayers,
  useMapLegend,
  useMapPins,
  type LegendEntry,
  type MapPin,
} from '../map/MapContext';
import { l5Layers } from '../map/l5-layers';
import styles from './TravellerView.module.css';

interface TravellerViewProps {
  /** Every finished version, in the menu's order: row 1's list. */
  readonly choices: readonly VersionChoice[];
  /** The version chosen: the one the route names. */
  readonly choice: VersionChoice;
  /** The route's `?period=`, or null for the version's first priced period. */
  readonly period: string | null;
  readonly onNavigate: (route: LabRoute) => void;
}

const ROUTE_FIT_PADDING = 40;

interface Typing {
  readonly field: PointField;
  readonly text: string;
}

/**
 * L-5, the traveller view: the pricing version first, then two points, then a time slot, and the
 * price of each way to travel under them. The route holds the version and the period; the points
 * stay in the view while the version is switched, and are quoted again with the new version.
 */
export function TravellerView({ choices, choice, period, onNavigate }: TravellerViewProps) {
  const [a, setA] = useState<GeoPoint | null>(null);
  const [b, setB] = useState<GeoPoint | null>(null);
  const [focused, setFocused] = useState<PointField | null>(null);
  const [typing, setTyping] = useState<Typing | null>(null);
  const [active, setActive] = useState(-1);

  const slots = useMemo(() => timeSlots(choice.periods), [choice.periods]);
  const periodKey =
    period !== null && slots.some((slot) => slot.key === period && slot.priced)
      ? period
      : (slots.find((slot) => slot.priced)?.key ?? choice.periods[0]?.key ?? null);
  const slot = slots.find((item) => item.key === periodKey);
  const range = slot?.range ?? choice.periods[0]?.label ?? '';

  const view = useInstanceView(choice.instanceVersionId).data;
  const geometry = useInstanceGeometry(choice.instanceVersionId).data;
  const counts = view?.version.counts ?? null;
  const parameters = view?.version.parameters ?? null;
  const centreLat = parameters?.centerLat;
  const centreLon = parameters?.centerLon;
  const radiusM = parameters?.radiusM;
  const circle = useMemo(
    () =>
      centreLat === undefined || centreLon === undefined || radiusM === undefined
        ? null
        : { centre: { lat: centreLat, lon: centreLon }, radiusM },
    [centreLat, centreLon, radiusM],
  );

  const setPoint = (field: PointField, point: GeoPoint) => {
    if (field === 'a') setA(point);
    else setB(point);
    setTyping((now) => (now?.field === field ? null : now));
    setActive(-1);
  };
  const inputs = useRef<Partial<Record<PointField, HTMLInputElement | null>>>({});
  useMapClick((point) => {
    setPoint(fieldForClick(focused, a), point);
    // The field kept while the map took the focus has been used: the next click follows the rule.
    const holder = document.activeElement;
    if (holder !== inputs.current.a && holder !== inputs.current.b) setFocused(null);
  });

  // The quote of the points set; the previous answer stays until the next one is read.
  const query = useTripQuote(choice.id, periodKey, a, b);
  const points = tripKey(periodKey, a, b);
  const answer = query.data;
  const placeholder = query.isPlaceholderData;
  const shown = useMemo<ShownQuote | null>(
    () =>
      answer === undefined || answer === null || placeholder
        ? null
        : {
            pricingVersionId: choice.id,
            instanceVersionId: choice.instanceVersionId,
            points,
            quote: answer,
          },
    [answer, placeholder, choice.id, choice.instanceVersionId, points],
  );
  const [track, setTrack] = useState<{
    shown: ShownQuote | null;
    previous: ShownQuote | null;
    /** The period the shown quote was read for. */
    period: string | null;
  }>({ shown: null, previous: null, period: null });
  if (shown !== null && track.shown !== shown) {
    setTrack({
      shown,
      previous: nextPrevious(track.shown, track.previous, shown),
      period: periodKey,
    });
  }
  const quote = track.shown?.quote ?? null;
  const previousPrices = track.previous === null ? null : cardPrices(track.previous.quote);
  const priced = quote !== null && (quote.status === 'priced' || quote.status === 'no_bike_option');

  // The selected card: the default one whenever a new quote shows, then the visitor's choice.
  const [picked, setPicked] = useState<{ for: ShownQuote | null; mode: QuotedMode } | null>(null);
  const selectedMode: QuotedMode | null =
    picked !== null && picked.for === track.shown
      ? picked.mode
      : quote === null
        ? null
        : defaultCard(quote);
  const selectedOption =
    quote === null
      ? undefined
      : quote.options.find((item) => item.mode === selectedMode && item.mostTaken);
  // The shown quote's own instance version and period: while the quote of a switched version or
  // time slot loads, the previous quote's route is never asked with the new choice.
  const routes = useRouteOptions(
    track.shown?.instanceVersionId ?? choice.instanceVersionId,
    track.period,
    priced ? (quote.originHub?.hubId ?? null) : null,
    priced ? (quote.destinationHub?.hubId ?? null) : null,
  ).data;
  const routeLegs = useMemo(
    () =>
      priced && selectedOption !== undefined
        ? (routes?.items.find((item) => item.arcId === selectedOption.arcId)?.legs ?? null)
        : null,
    [priced, selectedOption, routes],
  );
  const busShapes = routes?.busShapes ?? true;

  const fromHub = quote?.fromPoint?.hubId ?? null;
  const toHub = quote?.toPoint?.hubId ?? null;
  const declaration = useMemo(
    () =>
      geometry === undefined || circle === null
        ? null
        : l5Layers({
            centre: circle.centre,
            radiusM: circle.radiusM,
            stations: geometry.stations,
            hubs: geometry.hubs,
            matchedHubIds: [fromHub, toHub].filter((id): id is string => id !== null),
            route: routeLegs === null ? null : { legs: routeLegs },
          }),
    [geometry, circle, fromHub, toHub, routeLegs],
  );
  const bounds = useMemo<GeoBounds | null>(() => {
    if (routeLegs !== null) {
      const pins = [a, b].filter((point): point is GeoPoint => point !== null);
      const around = routeBounds(routeLegs, pins);
      if (around !== null) return around;
    }
    return circle === null ? null : circleBounds(circle.centre, circle.radiusM);
  }, [routeLegs, a, b, circle]);
  useMapLayers(declaration);
  useMapFit(bounds, routeLegs === null ? undefined : ROUTE_FIT_PADDING);
  const pins = useMemo<MapPin[]>(
    () => [
      ...(a === null ? [] : [{ point: a, label: 'Point A', text: 'A', colour: '#2e2d29' }]),
      ...(b === null ? [] : [{ point: b, label: 'Point B', text: 'B', colour: '#004494' }]),
    ],
    [a, b],
  );
  useMapPins(pins);
  const legend = useMemo<LegendEntry[]>(
    () =>
      routeLegs === null
        ? []
        : routeLegendKinds(routeLegs).map((kind) => ({
            label: ROUTE_STYLES[kind].label,
            colour: ROUTE_STYLES[kind].colour,
            dash: ROUTE_STYLES[kind].dash,
          })),
    [routeLegs],
  );
  useMapLegend(legend, routeLegs === null ? null : straightLegsSentence(busShapes));

  const names = usePlaceNames(choice.instanceVersionId, typing?.text ?? '');
  const lines: readonly PlaceLine[] =
    typing !== null && typing.text.trim().length >= 2 ? (names.data ?? []) : [];

  const fieldText = (field: PointField): string => {
    if (typing?.field === field) return typing.text;
    return pointFieldText(field === 'a' ? (quote?.fromPoint ?? null) : (quote?.toPoint ?? null));
  };
  const messages = [
    noHubMessage(quote?.fromPoint ?? null),
    noHubMessage(quote?.toPoint ?? null),
    ...(quote === null
      ? []
      : noPriceMessages(quote, choice.instanceVersionName, parameters?.radiusM ?? null)),
  ].filter((message): message is string => message !== null);

  const choose = (field: PointField, line: PlaceLine) => {
    setPoint(field, { lat: line.lat, lon: line.lon });
  };
  const onFieldKeyDown = (field: PointField) => (event: KeyboardEvent<HTMLInputElement>) => {
    if (typing?.field !== field || lines.length === 0) return;
    if (event.key === 'ArrowDown') setActive((now) => (now + 1) % lines.length);
    else if (event.key === 'ArrowUp') setActive((now) => (now <= 0 ? lines.length - 1 : now - 1));
    else if (event.key === 'Enter' && active >= 0) {
      const line = lines[active];
      if (line !== undefined) choose(field, line);
    } else return;
    event.preventDefault();
  };
  const swap = () => {
    setA(b);
    setB(a);
    setTyping(null);
  };

  const switchTo = (id: string) => {
    const next = choices.find((item) => item.id === id);
    if (next === undefined || next.id === choice.id) return;
    // An explicit period stays when the new version prices it; the default stays unwritten.
    const keep = next.periods.some((item) => item.key === period) ? period : null;
    onNavigate(
      travellerRoute({ instanceId: next.instanceId, version: next.number }, next.letter, keep),
    );
  };

  const listId = useId();
  const fieldInput = (field: PointField) => {
    const open = typing?.field === field && lines.length > 0;
    return (
      <div className={styles.field}>
        <span className={styles.tag} aria-hidden="true">
          {field.toUpperCase()}
        </span>
        <input
          className={styles.input}
          type="text"
          role="combobox"
          aria-label={`Point ${field.toUpperCase()}`}
          aria-expanded={open}
          aria-controls={`${listId}-${field}`}
          aria-autocomplete="list"
          aria-activedescendant={
            open && active >= 0 ? `${listId}-${field}-${String(active)}` : undefined
          }
          autoComplete="off"
          value={fieldText(field)}
          onFocus={() => {
            setFocused(field);
          }}
          ref={(element) => {
            inputs.current[field] = element;
          }}
          onBlur={(event) => {
            // A press on the map moves the focus to its canvas before the click arrives: the
            // field stays the one the click sets.
            if (event.relatedTarget instanceof HTMLCanvasElement) return;
            setFocused((now) => (now === field ? null : now));
          }}
          onChange={(event) => {
            setTyping({ field, text: event.target.value });
            setActive(-1);
          }}
          onKeyDown={onFieldKeyDown(field)}
        />
        {open && (
          <ul
            className={styles.list}
            role="listbox"
            id={`${listId}-${field}`}
            aria-label={`Names for point ${field.toUpperCase()}`}
          >
            {lines.map((line, at) => (
              // The keys belong to the combobox input (↑ / ↓ / Enter); a click is the pointer's way.
              // eslint-disable-next-line jsx-a11y/click-events-have-key-events
              <li
                key={`${line.name}-${line.kind}-${line.hubId}`}
                id={`${listId}-${field}-${String(at)}`}
                role="option"
                aria-selected={at === active}
                className={styles.option}
                onMouseDown={(event) => {
                  // Before the input loses focus, so the click still reaches the line.
                  event.preventDefault();
                }}
                onClick={() => {
                  choose(field, line);
                }}
              >
                {placeLine(line)}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  return (
    <div className={styles.view}>
      <p className={styles.brief}>{TRAVELLER_BRIEF.title}</p>
      <p className={styles.sentence}>{TRAVELLER_BRIEF.sentence}</p>

      <section className={styles.row} aria-labelledby={`${listId}-t1`}>
        <span className={styles.number} aria-hidden="true">
          1
        </span>
        <div className={styles.rowBody}>
          <h2 id={`${listId}-t1`} className={styles.rowTitle}>
            {ROW_TITLES.version}
          </h2>
          <select
            className={styles.select}
            aria-label={ROW_TITLES.version}
            value={choice.id}
            onChange={(event) => {
              switchTo(event.target.value);
            }}
          >
            {choices.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          {counts !== null && (
            <p className={styles.hint}>{instanceSentence(counts.hubs, counts.bikeStations)}</p>
          )}
        </div>
      </section>

      <section className={styles.row} aria-labelledby={`${listId}-t2`}>
        <span className={styles.number} aria-hidden="true">
          2
        </span>
        <div className={styles.rowBody}>
          <h2 id={`${listId}-t2`} className={styles.rowTitle}>
            {ROW_TITLES.trip}
          </h2>
          <div className={styles.fields}>
            {fieldInput('a')}
            <button type="button" className={styles.swap} aria-label={SWAP_LABEL} onClick={swap}>
              ⇅
            </button>
            {fieldInput('b')}
          </div>
          <p className={styles.hint}>{TRIP_SENTENCE}</p>
          {messages.length > 0 && (
            <div className={styles.message} role="status">
              {messages.map((message) => (
                <p key={message}>{message}</p>
              ))}
            </div>
          )}
        </div>
      </section>

      <section className={styles.row} aria-labelledby={`${listId}-t3`}>
        <span className={styles.number} aria-hidden="true">
          3
        </span>
        <div className={styles.rowBody}>
          <h2 id={`${listId}-t3`} className={styles.rowTitle}>
            {ROW_TITLES.slot}
          </h2>
          <div className={styles.slotRow}>
            <select className={styles.select} aria-label="Day" defaultValue={DAY_NAME}>
              <option value={DAY_NAME}>{DAY_NAME}</option>
            </select>
            <select
              className={styles.select}
              aria-label="Period"
              value={periodKey ?? ''}
              onChange={(event) => {
                onNavigate(
                  travellerRoute(
                    { instanceId: choice.instanceId, version: choice.number },
                    choice.letter,
                    event.target.value,
                  ),
                );
              }}
            >
              {slots.map((item) => (
                <option key={item.key} value={item.key} disabled={!item.priced}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
          <span className={styles.nextTag}>{NEXT_VERSION_TAG}</span>
          <span className={styles.hint}>{NEXT_VERSION_TEXT}</span>
        </div>
      </section>

      {priced && (
        <section aria-label="Options and prices" className={styles.options}>
          <div className={styles.optionsHead}>
            <h3 className={styles.heading}>{quoteHeading(quote)}</h3>
            <p className={styles.scope}>{scopeLine(range, choice.letter)}</p>
          </div>
          <ul className={styles.cards}>
            {OPTION_CARDS.flatMap((card) => {
              const option = quote.options.find(
                (item) => item.mode === card.mode && item.mostTaken,
              );
              if (option === undefined) {
                const missing =
                  card.mode === 'pt_bike' && quote.status === 'no_bike_option'
                    ? noBikeOption(choice.letter)
                    : card.mode === 'car' && quote.noCarOption === true
                      ? NO_CAR_ROUTE
                      : null;
                return missing === null
                  ? []
                  : [
                      <li
                        key={card.mode}
                        className={styles.card}
                        data-mode={card.mode}
                        data-testid={`card-${card.mode}`}
                      >
                        <p className={styles.missing}>{missing}</p>
                      </li>,
                    ];
              }
              return [
                <OptionCard
                  // A new trip is a new card: the other bike options list closes; a version
                  // switch on the same trip keeps it.
                  key={`${card.mode}:${track.shown?.points ?? ''}`}
                  card={card}
                  option={option}
                  others={card.mode === 'pt_bike' ? otherBikeOptions(quote) : []}
                  before={previousPrices?.get(card.mode)}
                  selected={card.mode === selectedMode}
                  onSelect={() => {
                    setPicked({ for: track.shown, mode: card.mode });
                  }}
                />,
              ];
            })}
          </ul>
          <div className={styles.notes}>
            {TRAVELLER_NOTES.map((note) => (
              <p key={note}>{note}</p>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
