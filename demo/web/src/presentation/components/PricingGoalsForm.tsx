import { useState } from 'react';
import { draftSaved } from '../../domain/draft-text';
import { versionTag } from '../../domain/l1-text';
import {
  BALANCE_FIELD,
  COST_FIELD,
  EXPLAIN_LABEL,
  KEPT_FIELDS,
  LOWEST_FIELD,
  NAME_LABEL,
  NAME_PLACEHOLDER,
  NEXT_VERSION,
  NEXT_VERSION_TAG,
  PERIOD_HOURS,
  PERIOD_SENTENCE,
  PRICING_BRIEF,
  PRICING_HEADING,
  PRICING_SENTENCE,
  PROFIT_FIXED,
  PROFIT_LABEL,
  PROFIT_SENTENCE,
  RIDERSHIP_FIELD,
  RULES_BEFORE_RUNNING,
  RUN_LABEL,
  SEALED_NOTE,
  SELECTED_HOUR,
  STEP_1,
  STEP_2,
  STEP_3,
  bannerWithStoredResults,
  costMessage,
  discardQuestion,
  failedFields,
  goalBars,
  goalText,
  hourLabel,
  parseGoalInput,
  pricingBannerSentences,
  pricingPrimaryState,
  rankingLine,
  ruleLines,
  step4Heading,
  thisRunLine,
  type ExplainTopic,
  type GoalField,
} from '../../domain/pricing-goals-text';
import {
  isDefaultName,
  pricingVersionId,
  type PricingChanges,
  type PricingGoalName,
  type PricingGoals,
  type PricingVersion,
} from '../../domain/pricing-version';
import type { LabRoute } from '../../domain/route';
import { missingPricingVersionLabel, nothingAtThisLink } from '../../domain/unknown-link';
import { useInstanceView } from '../hooks/useCityInstances';
import { useAutosave } from '../hooks/useAutosave';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { usePricingActions, usePricingVersion } from '../hooks/usePricingVersions';
import { LoadingCard } from './LoadingCard';
import { PricingDetailsPanel } from './PricingDetailsPanel';
import styles from './PricingGoalsForm.module.css';

interface PricingGoalsFormProps {
  readonly instanceVersionId: string;
  readonly instanceId: string;
  readonly number: number;
  readonly letter: string;
  readonly advancedView: boolean;
  readonly onNavigate: (route: LabRoute) => void;
}

interface EditorProps extends Omit<PricingGoalsFormProps, 'letter'> {
  readonly version: PricingVersion;
  readonly instanceLabel: string;
  readonly hubPairs: number | null;
}

function StepHead({
  step,
  heading,
  explain,
}: {
  step: { readonly number: number; readonly unit: string | null };
  heading: string;
  explain?: { readonly topic: ExplainTopic; readonly open: () => void };
}) {
  return (
    <h3 className={styles.stepHead}>
      <span className={styles.stepNumber} aria-hidden="true">
        {step.number}
      </span>
      <span>{heading}</span>
      {step.unit !== null && <small className={styles.stepUnit}>{step.unit}</small>}
      {explain !== undefined && (
        <button
          type="button"
          className={styles.explain}
          data-explain={explain.topic}
          onClick={explain.open}
        >
          {EXPLAIN_LABEL} <span className={styles.srOnly}>step {step.number}</span>
        </button>
      )}
    </h3>
  );
}

function Editor({
  version,
  instanceId,
  number,
  instanceLabel,
  hubPairs,
  advancedView,
  onNavigate,
}: EditorProps) {
  const actions = usePricingActions();
  const status = useSystemStatus().data;
  const kept = usePricingVersion(version.keptFrom?.id ?? null).data ?? null;
  const sealed = version.status === 'sealed';

  const [goals, setGoals] = useState<PricingGoals>(version.goals);
  const [texts, setTexts] = useState<Partial<Record<PricingGoalName, string>>>({});
  const [nameText, setNameText] = useState(!sealed && isDefaultName(version) ? '' : version.name);
  const [savedAt, setSavedAt] = useState<Date | null>(null);
  const [panel, setPanel] = useState<ExplainTopic | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [openedFrom, setOpenedFrom] = useState<ExplainTopic>('period');

  const reportFailure = (error: unknown) => {
    setFailure(error instanceof Error ? error.message : String(error));
  };

  const autosave = useAutosave<PricingChanges>(async (changes) => {
    try {
      await actions.patch(version.id, changes);
    } catch (error) {
      // Kept pending by the autosave; the next change or the run sends it again.
      reportFailure(error);
      throw error;
    }
    setFailure(null);
    setSavedAt(new Date());
  });

  // Once the run or the discard is sent, a change would reach a sealed or deleted draft.
  const closing = actions.run.isPending || actions.discard.isPending;
  const readOnly = sealed || closing;

  const onType = (name: PricingGoalName, text: string) => {
    if (readOnly) return;
    setTexts((previous) => ({ ...previous, [name]: text }));
    const typed = parseGoalInput(text);
    if (typed === null) return;
    setGoals((previous) => ({ ...previous, [name]: typed }));
    setRunNote(null);
    autosave.schedule({ [name]: typed });
  };
  const endTyping = (name: PricingGoalName) => {
    setTexts((previous) => {
      const rest = { ...previous };
      Reflect.deleteProperty(rest, name);
      return rest;
    });
  };
  const onName = (text: string) => {
    if (readOnly) return;
    setNameText(text);
    const trimmed = text.trim();
    // An empty input keeps the stored name; it also replaces a typed name still pending.
    autosave.schedule({ name: trimmed === '' ? version.name : trimmed });
  };

  const openPanel = (topic: ExplainTopic) => () => {
    setOpenedFrom(topic);
    setPanel(topic);
  };
  const closePanel = () => {
    setPanel(null);
    // The button of the step that opened it is always on the page.
    document.querySelector<HTMLElement>(`[data-explain="${openedFrom}"]`)?.focus();
  };

  const openInstance = () => {
    onNavigate({ kind: 'instance', instance: { instanceId, version: number }, period: null });
  };
  const discard = () => {
    autosave.cancel();
    // After the send in flight, so that no PATCH reaches the draft once it is deleted.
    autosave.after(() => actions.discard.mutateAsync(version)).then(openInstance, reportFailure);
  };
  const run = () => {
    setRunNote(null);
    actions.run.mutateAsync({ id: version.id, flush: autosave.flush }).then((result) => {
      if (result.kind === 'refused') setRunNote(result.detail);
    }, reportFailure);
  };

  const failed = failedFields(version.rules);
  const primary = pricingPrimaryState(version.rules, status);
  const note = runNote ?? primary.note;
  const banners = pricingBannerSentences(status);
  const cost = costMessage(goals.cost_bike_chf, goals.lowest_price_chf);
  const bars = goalBars(goals);
  const previous = (field: GoalField): number | null => {
    if (kept === null || sealed) return null;
    const before = kept.goals[field.name];
    return before === goals[field.name] ? null : before;
  };

  const renderField = (field: GoalField) => {
    const before = previous(field);
    const value = texts[field.name] ?? goalText(field, goals[field.name]);
    return (
      <div key={field.name} className={styles.field} role="group" aria-label={field.label}>
        <span className={styles.label}>
          {field.label}
          {advancedView && field.packageName !== null && (
            <code className={styles.package}>{field.packageName}</code>
          )}
        </span>
        <span className={styles.inputs}>
          {before !== null && <s className={styles.was}>{goalText(field, before)}</s>}
          <input
            className={styles.input}
            inputMode="decimal"
            aria-label={field.label}
            aria-invalid={failed.has(field.name)}
            readOnly={readOnly}
            value={value}
            onChange={(event) => {
              onType(field.name, event.target.value);
            }}
            onBlur={() => {
              endTyping(field.name);
            }}
          />
          {field.unit !== null && <span className={styles.unit}>{field.unit}</span>}
        </span>
        <p className={styles.sentence}>{field.sentence(goals)}</p>
      </div>
    );
  };

  const renderWeight = (field: GoalField, share: number) => {
    const before = previous(field);
    return (
      <div key={field.name} className={styles.field} role="group" aria-label={field.label}>
        <span className={styles.label}>
          {field.label}
          {advancedView && field.packageName !== null && (
            <code className={styles.package}>{field.packageName}</code>
          )}
        </span>
        <span className={styles.bar} role="img" aria-label={`${field.label} bar`}>
          <i style={{ width: `${String(share * 100)}%` }} />
        </span>
        <span className={styles.inputs}>
          {before !== null && <s className={styles.was}>{goalText(field, before)}</s>}
          <input
            className={styles.input}
            inputMode="decimal"
            aria-label={`${field.label} weight`}
            aria-invalid={failed.has(field.name)}
            readOnly={readOnly}
            value={texts[field.name] ?? goalText(field, goals[field.name])}
            onChange={(event) => {
              onType(field.name, event.target.value);
            }}
            onBlur={() => {
              endTyping(field.name);
            }}
          />
        </span>
        <p className={styles.sentence}>{field.sentence(goals)}</p>
      </div>
    );
  };

  const [profitBar, ridershipBar, balanceBar] = bars;

  return (
    <div className={styles.work} data-details={String(panel !== null)}>
      <div className={styles.view}>
        <p className={styles.brief}>
          <span className={styles.rhythm}>{PRICING_BRIEF}</span>
          <span>{PRICING_SENTENCE}</span>
        </p>
        <div className={styles.head}>
          <h2 className={styles.title}>{PRICING_HEADING}</h2>
          {savedAt !== null && <span className={styles.scope}>{draftSaved(savedAt)}</span>}
        </div>
        <div className={styles.nameRow}>
          <label className={styles.label} htmlFor="pricing-name">
            {NAME_LABEL}
          </label>
          <input
            id="pricing-name"
            className={styles.nameInput}
            value={nameText}
            placeholder={NAME_PLACEHOLDER}
            maxLength={120}
            readOnly={readOnly}
            onChange={(event) => {
              onName(event.target.value);
            }}
          />
        </div>
        {sealed && <p className={styles.sentence}>{SEALED_NOTE}</p>}

        <div className={styles.steps}>
          <div className={styles.column}>
            <section aria-label={STEP_1.title}>
              <StepHead
                step={STEP_1}
                heading={STEP_1.title}
                explain={{ topic: 'period', open: openPanel('period') }}
              />
              <div className={styles.hours} role="group" aria-label="Periods to price, Monday">
                {PERIOD_HOURS.map((hour) =>
                  hour === SELECTED_HOUR ? (
                    <button
                      key={hour}
                      type="button"
                      className={styles.hour}
                      aria-pressed="true"
                      aria-label={hourLabel(hour)}
                    >
                      {hour}
                    </button>
                  ) : (
                    <button
                      key={hour}
                      type="button"
                      className={styles.hour}
                      disabled
                      title={NEXT_VERSION}
                      aria-label={hourLabel(hour)}
                    >
                      {hour}
                    </button>
                  ),
                )}
              </div>
              <p className={styles.sentence}>
                {PERIOD_SENTENCE} <span className={styles.tag}>{NEXT_VERSION_TAG}</span>
              </p>
            </section>
            <section aria-label={STEP_2.title}>
              <StepHead
                step={STEP_2}
                heading={STEP_2.title}
                explain={{ topic: 'price', open: openPanel('price') }}
              />
              {renderField(COST_FIELD)}
              {renderField(LOWEST_FIELD)}
              <div className={styles.message} data-tone={cost.tone}>
                <b>{cost.lead}</b> {cost.rest}
              </div>
            </section>
          </div>

          <div className={styles.column}>
            <section aria-label={STEP_3.title}>
              <StepHead
                step={STEP_3}
                heading={STEP_3.title}
                explain={{ topic: 'weights', open: openPanel('weights') }}
              />
              <div className={styles.field} role="group" aria-label={PROFIT_LABEL}>
                <span className={styles.label}>{PROFIT_LABEL}</span>
                <span className={styles.bar} role="img" aria-label={`${PROFIT_LABEL} bar`}>
                  <i style={{ width: `${String((profitBar?.share ?? 0) * 100)}%` }} />
                </span>
                <span className={styles.fixed}>{PROFIT_FIXED}</span>
                <p className={styles.sentence}>{PROFIT_SENTENCE}</p>
              </div>
              {renderWeight(RIDERSHIP_FIELD, ridershipBar?.share ?? 0)}
              {renderWeight(BALANCE_FIELD, balanceBar?.share ?? 0)}
              <p className={styles.ranking}>{rankingLine(goals)}</p>
            </section>
            <section aria-label={step4Heading(version.keptFrom)}>
              <StepHead step={{ number: 4, unit: null }} heading={step4Heading(version.keptFrom)} />
              {KEPT_FIELDS.map(renderField)}
            </section>
            <section className={styles.rulesBox} aria-label={RULES_BEFORE_RUNNING}>
              <h3>{RULES_BEFORE_RUNNING}</h3>
              <ul className={styles.rules}>
                {ruleLines(version.rules).map((line) => (
                  <li key={line.key} className={styles.rule} data-passed={String(line.passed)}>
                    <span className={styles.mark} aria-hidden="true">
                      {line.passed ? '✓' : '✕'}
                    </span>
                    {line.text}
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>

        <p className={styles.runLine}>
          {thisRunLine(instanceLabel, hubPairs, version.lastDurationS).map((part) => (
            <span key={part}>{part}</span>
          ))}
        </p>

        {!sealed && (
          <>
            {banners.length > 0 && (
              <div className={styles.banners}>
                {banners.map((sentence) => (
                  <p key={sentence} className={styles.banner}>
                    {bannerWithStoredResults(sentence)}
                  </p>
                ))}
              </div>
            )}
            <div className={styles.actions}>
              <button
                type="button"
                className={styles.primary}
                disabled={primary.disabled || actions.run.isPending}
                onClick={run}
              >
                {RUN_LABEL}
              </button>
              {confirming ? (
                <span className={styles.confirm}>
                  <span>{discardQuestion(version.keptFrom)}</span>
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
                <span
                  className={runNote === null && primary.disabled ? styles.noteBad : styles.note}
                >
                  {note}
                </span>
              )}
            </div>
          </>
        )}
        {failure !== null && <p className={styles.error}>{failure}</p>}
      </div>
      {panel !== null && (
        <PricingDetailsPanel topic={panel} goals={goals} onTopic={setPanel} onClose={closePanel} />
      )}
    </div>
  );
}

/** L-2: the pricing goals of one pricing version of a built instance version. */
export function PricingGoalsForm(props: PricingGoalsFormProps) {
  const id = pricingVersionId(props.instanceVersionId, props.letter);
  const query = usePricingVersion(id);
  const view = useInstanceView(props.instanceVersionId);
  if (query.isPending || view.isPending) return <LoadingCard />;
  if (query.isError || view.isError) {
    const message = query.error?.message ?? view.error?.message ?? '';
    return <p className={styles.error}>The pricing version could not be read: {message}</p>;
  }
  const instanceName = view.data?.instanceName ?? props.instanceId;
  const label = `${instanceName} ${versionTag(props.number)}`;
  if (query.data === null) {
    return <p>{nothingAtThisLink(label, missingPricingVersionLabel(props.letter))}</p>;
  }
  return (
    <Editor
      key={query.data.id}
      {...props}
      version={query.data}
      instanceLabel={label}
      hubPairs={view.data?.version.counts?.hubPairsWithRoutes ?? null}
    />
  );
}
