import { useMemo, useRef, useState } from 'react';
import type { InstanceView as InstanceViewValue } from '../../application/use-cases/load-instance-view';
import {
  PARAMETER_KEYS,
  type InstanceParameters,
  type ParameterName,
} from '../../domain/city-instance';
import {
  CENTRE_SENTENCE,
  FIELD_INPUTS,
  RADIUS_SENTENCE,
  RESTORE_LABEL,
  RESTORE_TITLE,
  ROUTING_DATE_RULE,
  bannerSentences,
  discardQuestion,
  draftHeading,
  draftSaved,
  inputText,
  parseInput,
  primaryLabel,
  primaryState,
  routingDateLine,
  ruleFields,
  STORED_STAY,
  valueText,
  versionNumberOf,
} from '../../domain/draft-text';
import { L1_BRIEF, L1_SENTENCE, l1Groups } from '../../domain/l1-text';
import { circleBounds } from '../../domain/map';
import type { LabRoute } from '../../domain/route';
import {
  useDraftActions,
  useInstanceMenu,
  useInstanceView,
  useNewInstanceBasis,
} from '../hooks/useCityInstances';
import { useAutosave } from '../hooks/useAutosave';
import { MAP_COLOURS } from '../map/basemap-style';
import { l1Layers } from '../map/l1-layers';
import {
  useMapFit,
  useMapHandles,
  useMapLayers,
  useMapLegend,
  type LegendEntry,
} from '../map/MapContext';
import { ChangesTable } from './ChangesTable';
import { LoadingCard } from './LoadingCard';
import { NewInstanceHeader } from './NewInstanceHeader';
import { RulesBox } from './RulesBox';
import { SaveBox } from './SaveBox';
import styles from './DraftForm.module.css';

const STUDY_LEGEND: readonly LegendEntry[] = [
  { label: 'Study zone: drag the centre or the edge', colour: MAP_COLOURS.ring },
];

interface DraftFormProps {
  readonly versionId: string;
  readonly advancedView: boolean;
  readonly onNavigate: (route: LabRoute) => void;
  /** Shown above the form, e.g. that the instance already had this draft. */
  readonly notice?: string | null;
}

function without(
  texts: Partial<Record<ParameterName, string>>,
  names: readonly ParameterName[],
): Partial<Record<ParameterName, string>> {
  const rest = { ...texts };
  for (const name of names) Reflect.deleteProperty(rest, name);
  return rest;
}

function withValues(values: InstanceParameters, changes: Partial<Record<ParameterName, number>>) {
  const next: Record<string, number> = { ...values };
  for (const [name, value] of Object.entries(changes) as [ParameterName, number][]) {
    next[PARAMETER_KEYS[name]] = value;
  }
  return next as unknown as InstanceParameters;
}

function Editor({
  view,
  advancedView,
  onNavigate,
  notice,
}: { view: InstanceViewValue } & Omit<DraftFormProps, 'versionId'>) {
  const { version, instanceName, dataset } = view;
  const isNew = version.number === 1;
  const basedNumber = version.basedOnId === null ? null : versionNumberOf(version.basedOnId);
  const actions = useDraftActions();
  const menu = useInstanceMenu().data;
  const basis = useNewInstanceBasis().data;

  const [values, setValues] = useState<InstanceParameters>(version.parameters);
  const [texts, setTexts] = useState<Partial<Record<ParameterName, string>>>({});
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [startFrom, setStartFrom] = useState(
    version.basedOnId === null ? 'defaults' : `copy:${version.basedOnId}`,
  );
  const [confirming, setConfirming] = useState(false);
  const [buildNote, setBuildNote] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  function reportFailure(error: unknown) {
    setFailure(error instanceof Error ? error.message : String(error));
  }
  // The changes made since a restore or a "Start from" was sent: its answer must not undo them.
  const since = useRef<Partial<Record<ParameterName, number>>>({});

  const autosave = useAutosave(async (changes) => {
    try {
      await actions.patch(version.id, changes);
    } catch (error) {
      // Kept pending by the autosave; the next change or "Save and build" sends it again.
      reportFailure(error);
      throw error;
    }
    setFailure(null);
    setSavedAt(new Date());
  });

  // Once the build or the discard is sent, a change would reach a sealed or deleted draft.
  const closing = actions.build.isPending || actions.discard.isPending;
  const change = (changes: Partial<Record<ParameterName, number>>) => {
    if (closing) return;
    since.current = { ...since.current, ...changes };
    setValues((previous) => withValues(previous, changes));
    setBuildNote(null);
    autosave.schedule(changes);
  };

  const onType = (param: ParameterName, text: string) => {
    setTexts((previous) => ({ ...previous, [param]: text }));
    const typed = parseInput(param, text);
    if (typed !== null) change({ [param]: typed });
  };
  const endTyping = (param: ParameterName) => {
    setTexts((previous) => without(previous, [param]));
  };

  const circle = useMemo(
    () => ({ centre: { lat: values.centerLat, lon: values.centerLon }, radiusM: values.radiusM }),
    [values.centerLat, values.centerLon, values.radiusM],
  );
  const declaration = useMemo(
    () => l1Layers({ ...circle, stations: [], hubs: [], hubPairs: [] }),
    [circle],
  );
  // The map looks at the circle the form opened with; dragging must not move the camera.
  const [bounds] = useState(() =>
    circleBounds(
      { lat: version.parameters.centerLat, lon: version.parameters.centerLon },
      version.parameters.radiusM,
    ),
  );
  useMapLayers(declaration);
  useMapFit(bounds);
  useMapLegend(STUDY_LEGEND);
  useMapHandles(
    circle,
    (centre) => {
      setTexts((previous) => without(previous, ['center_lat', 'center_lon']));
      change({ center_lat: centre.lat, center_lon: centre.lon });
    },
    (radiusM) => {
      setTexts((previous) => without(previous, ['radius_m']));
      change({ radius_m: radiusM });
    },
  );

  const adopt = (answer: InstanceParameters) => {
    const newer = since.current;
    setValues(withValues(answer, newer));
    setTexts((previous) => {
      const kept: Partial<Record<ParameterName, string>> = {};
      for (const name of Object.keys(newer) as ParameterName[]) {
        const text = previous[name];
        if (text !== undefined) kept[name] = text;
      }
      return kept;
    });
    setSavedAt(new Date());
  };
  const restore = () => {
    autosave.cancel();
    since.current = {};
    setBuildNote(null);
    setStartFrom('defaults');
    if (version.packageDefaults !== null) {
      setValues(version.packageDefaults);
      setTexts({});
    }
    // After the send in flight: its answer must not land after this one.
    autosave
      .after(() => actions.restoreDefaults(version))
      .then((answer) => {
        adopt(answer.parameters);
      }, reportFailure);
  };
  const chooseStart = (choice: string) => {
    setStartFrom(choice);
    autosave.cancel();
    since.current = {};
    const source =
      choice === 'defaults'
        ? ({ kind: 'package_defaults' } as const)
        : ({ kind: 'copy', versionId: choice.slice('copy:'.length) } as const);
    autosave
      .after(() => actions.startFrom(version, source))
      .then((answer) => {
        adopt(answer.parameters);
      }, reportFailure);
  };
  const open = (number: number | null) => {
    onNavigate(
      number === null
        ? { kind: 'lab', period: null }
        : {
            kind: 'instance',
            instance: { instanceId: version.instanceId, version: number },
            period: null,
          },
    );
  };
  const discard = () => {
    autosave.cancel();
    // After the send in flight, so that no PATCH reaches the draft once it is deleted.
    autosave
      .after(() => actions.discard.mutateAsync(version.id))
      .then(() => {
        open(basedNumber);
      }, reportFailure);
  };
  const build = () => {
    setBuildNote(null);
    actions.build.mutateAsync({ id: version.id, flush: autosave.flush }).then((result) => {
      if (result.kind === 'queued') open(version.number);
      else setBuildNote(result.detail);
    }, reportFailure);
  };

  const failed = new Set(
    version.rules.filter((rule) => !rule.passed).flatMap((rule) => ruleFields(rule)),
  );
  const primary = primaryState({
    rules: version.rules,
    edit: !isNew,
    basedNumber,
    plan: version.buildPlan,
    changes: version.changes,
  });
  const note = buildNote ?? primary.note;
  const changed = new Map(version.changes.map((entry) => [entry.parameter, entry.before]));
  const pricingVersions =
    menu
      ?.find((entry) => entry.id === version.instanceId)
      ?.versions.find((candidate) => candidate.id === version.basedOnId)?.pricingVersionCount ?? 0;
  const groups = l1Groups({ parameters: values, periods: version.periods }, dataset)
    .map((group) => ({
      ...group,
      // The new-instance form shows the city data above the groups.
      fields: isNew ? group.fields.filter((item) => item.name !== 'City data') : group.fields,
    }))
    .filter((group) => group.fields.length > 0);
  const [period] = version.periods;
  const routingRule = version.rules.find((rule) => rule.rule === ROUTING_DATE_RULE);

  return (
    <div className={styles.view}>
      <p className={styles.brief}>
        <span className={styles.rhythm}>{L1_BRIEF}</span>
        <span>{L1_SENTENCE}</span>
      </p>
      <div className={styles.head}>
        <h2 className={styles.name}>{draftHeading(instanceName)}</h2>
        {savedAt !== null && <span className={styles.scope}>{draftSaved(savedAt)}</span>}
      </div>
      {notice !== undefined && notice !== null && <p className={styles.notice}>{notice}</p>}
      {isNew && (
        <NewInstanceHeader
          name={instanceName}
          nameNote={null}
          datasetName={dataset.name}
          copies={basis?.copies ?? []}
          startFrom={startFrom}
          onStartFrom={chooseStart}
        />
      )}
      {groups.map((group) => (
        <section key={group.number} className={styles.group} aria-label={group.name}>
          <h3 className={styles.groupHead}>
            <span className={styles.groupNumber} aria-hidden="true">
              {group.number}
            </span>
            {group.name}
          </h3>
          {group.fields.map((field) => {
            const inputs = FIELD_INPUTS[field.packageNames] ?? [];
            const sentence =
              field.packageNames === 'center_lat · center_lon'
                ? CENTRE_SENTENCE
                : field.packageNames === 'radius_m'
                  ? RADIUS_SENTENCE
                  : field.sentence;
            return (
              <div key={field.name} className={styles.field} role="group" aria-label={field.name}>
                <span className={styles.label}>
                  {field.name}
                  {advancedView && <code className={styles.package}>{field.packageNames}</code>}
                </span>
                {inputs.length === 0 ? (
                  <span className={styles.value}>{field.value}</span>
                ) : (
                  <div className={styles.inputs}>
                    {inputs.map((input) => {
                      const key = PARAMETER_KEYS[input.param];
                      const before = changed.get(input.param);
                      return (
                        <span key={input.param}>
                          {before !== undefined && (
                            <s className={styles.was}>{valueText(input.param, before)}</s>
                          )}{' '}
                          <input
                            className={styles.input}
                            inputMode="decimal"
                            aria-label={input.label}
                            aria-invalid={failed.has(input.param)}
                            readOnly={closing}
                            value={texts[input.param] ?? inputText(input.param, values[key])}
                            onChange={(event) => {
                              onType(input.param, event.target.value);
                            }}
                            onBlur={() => {
                              endTyping(input.param);
                            }}
                          />
                          {input.unit !== null && (
                            <span className={styles.unit}> {input.unit}</span>
                          )}
                        </span>
                      );
                    })}
                  </div>
                )}
                {sentence !== null && <p className={styles.sentence}>{sentence}</p>}
                {field.caption !== null && <p className={styles.caption}>{field.caption}</p>}
                {field.packageNames === 'otp_timestamp' && period !== undefined && (
                  <RoutingDate
                    line={routingDateLine(routingRule, period, {
                      from: dataset.timetableValidFrom,
                      to: dataset.timetableValidTo,
                    })}
                  />
                )}
              </div>
            );
          })}
        </section>
      ))}
      <RulesBox rules={version.rules} />
      {!isNew && basedNumber !== null && (
        <>
          <SaveBox
            name={instanceName}
            draftNumber={version.number}
            basedNumber={basedNumber}
            pricingVersions={pricingVersions}
            plan={version.buildPlan}
          />
          <ChangesTable
            changes={version.changes}
            plan={version.buildPlan}
            draftNumber={version.number}
            basedNumber={basedNumber}
            bikeStationsFetchedAt={dataset.bikeStationsFetchedAt}
          />
        </>
      )}
      {bannerSentences(version.buildPlan).length > 0 && (
        <div className={styles.banners}>
          {bannerSentences(version.buildPlan).map((sentence) => (
            <p key={sentence} className={styles.banner}>
              {`${sentence} ${STORED_STAY}`}
            </p>
          ))}
        </div>
      )}
      <div className={styles.actions}>
        <button
          type="button"
          className={styles.primary}
          disabled={primary.disabled || actions.build.isPending}
          onClick={build}
        >
          {primaryLabel(version.number)}
        </button>
        <button type="button" className={styles.secondary} title={RESTORE_TITLE} onClick={restore}>
          {RESTORE_LABEL}
        </button>
        {confirming ? (
          <span className={styles.confirm}>
            <span>{discardQuestion(isNew ? null : basedNumber)}</span>
            <button
              type="button"
              className={styles.secondary}
              disabled={actions.discard.isPending}
              onClick={discard}
            >
              Discard draft
            </button>
            <button
              type="button"
              className={styles.secondary}
              onClick={() => {
                setConfirming(false);
              }}
            >
              Keep
            </button>
          </span>
        ) : (
          <button
            type="button"
            className={styles.secondary}
            onClick={() => {
              setConfirming(true);
            }}
          >
            Discard draft
          </button>
        )}
        {note !== null && (
          <span className={buildNote === null && primary.disabled ? styles.noteBad : styles.note}>
            {note}
          </span>
        )}
      </div>
      {failure !== null && <p className={styles.error}>{failure}</p>}
    </div>
  );
}

function RoutingDate({ line }: { line: { passed: boolean; text: string } }) {
  return (
    <p className={styles.sentence} data-passed={String(line.passed)}>
      <span className={styles.mark} aria-hidden="true">
        {line.passed ? '✓' : '✕'}
      </span>
      {line.text}
    </p>
  );
}

/** The draft of a city instance version: the edit form, or the new-instance form for a first version. */
export function DraftForm({ versionId, advancedView, onNavigate, notice = null }: DraftFormProps) {
  const query = useInstanceView(versionId);
  if (query.isPending) return <LoadingCard />;
  if (query.isError) {
    return (
      <p className={styles.error}>The city instance could not be read: {query.error.message}</p>
    );
  }
  if (query.data === null) return <p>Nothing at this link.</p>;
  return (
    <Editor
      key={query.data.version.id}
      view={query.data}
      advancedView={advancedView}
      onNavigate={onNavigate}
      notice={notice}
    />
  );
}
