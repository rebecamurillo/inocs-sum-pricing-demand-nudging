import { useEffect, useRef } from 'react';
import {
  DETAILS_HEADING,
  EXPLAIN_TABS,
  NEXT_VERSION_TAG,
  PERIOD_TEXTS,
  PRICE_TEXTS,
  SOURCE_LINE,
  WEIGHT_TEXTS,
  exampleRide,
  numberLine,
  type ExplainTopic,
} from '../../domain/pricing-goals-text';
import type { PricingGoals } from '../../domain/pricing-version';
import styles from './PricingDetailsPanel.module.css';

interface PricingDetailsPanelProps {
  readonly topic: ExplainTopic;
  readonly goals: PricingGoals;
  readonly onTopic: (topic: ExplainTopic) => void;
  readonly onClose: () => void;
}

function PeriodTab() {
  return (
    <section>
      <h4>{PERIOD_TEXTS.heading}</h4>
      <p>{PERIOD_TEXTS.prices}</p>
      <p>{PERIOD_TEXTS.instance}</p>
      <p>
        <span className={styles.tag}>{NEXT_VERSION_TAG}</span> {PERIOD_TEXTS.next}
      </p>
    </section>
  );
}

function PriceTab({ goals }: { goals: PricingGoals }) {
  const line = numberLine(goals.cost_bike_chf, goals.lowest_price_chf);
  return (
    <>
      <section>
        <h4>{PRICE_TEXTS.lineHeading}</h4>
        <div className={styles.line} role="img" aria-label={line.caption}>
          <div className={styles.axis} />
          <div className={styles.band} style={{ left: `${String(line.lowestAt)}%` }} />
          {line.loss !== null && (
            <div
              className={styles.loss}
              data-testid="loss"
              style={{
                left: `${String(line.loss.from)}%`,
                width: `${String(line.loss.to - line.loss.from)}%`,
              }}
            />
          )}
          <div className={styles.markCost} style={{ left: `${String(line.costAt)}%` }}>
            <span>{PRICE_TEXTS.costMark(goals.cost_bike_chf)}</span>
          </div>
          <div className={styles.markLowest} style={{ left: `${String(line.lowestAt)}%` }}>
            <span>{PRICE_TEXTS.lowestMark(goals.lowest_price_chf)}</span>
          </div>
          {line.ticks.map((tick) => (
            <span key={tick.label} className={styles.tick} style={{ left: `${String(tick.at)}%` }}>
              {tick.label}
            </span>
          ))}
        </div>
        <p className={styles.caption}>{line.caption}</p>
      </section>
      <section>
        <h4>{PRICE_TEXTS.profitHeading}</h4>
        <p>{PRICE_TEXTS.profit}</p>
      </section>
      <section>
        <h4>{PRICE_TEXTS.highestHeading}</h4>
        <p>{PRICE_TEXTS.highest}</p>
      </section>
    </>
  );
}

const ZERO_AT = 16;

function WeightsTab({ goals }: { goals: PricingGoals }) {
  const ride = exampleRide(goals);
  return (
    <>
      <section>
        <h4>{WEIGHT_TEXTS.heading}</h4>
        <p>{WEIGHT_TEXTS.example}</p>
        <div className={styles.parts}>
          {ride.parts.map((part) => {
            const width = Math.abs(part.share) * (part.share < 0 ? ZERO_AT : 100 - ZERO_AT);
            return (
              <div key={part.label} className={styles.part}>
                <span>{part.label}</span>
                <span className={styles.track} data-negative={String(part.share < 0)}>
                  <i
                    style={
                      part.share < 0
                        ? { left: `${String(ZERO_AT - width)}%`, width: `${String(width)}%` }
                        : { left: `${String(ZERO_AT)}%`, width: `${String(Math.max(width, 1))}%` }
                    }
                  />
                </span>
                <span className={styles.amount}>
                  {part.value < 0 ? '' : '+ '}
                  {part.amount}
                </span>
              </div>
            );
          })}
        </div>
        <p className={styles.total}>
          <span>{WEIGHT_TEXTS.total}</span>
          <span className={styles.amount}>{ride.totalText}</span>
        </p>
        <p>{ride.sentence}</p>
      </section>
      <section>
        <h4>{WEIGHT_TEXTS.readingHeading}</h4>
        <p>{WEIGHT_TEXTS.reading}</p>
      </section>
    </>
  );
}

/** "How the model reads these values": one tab per step, the values of the form read through. */
export function PricingDetailsPanel({ topic, goals, onTopic, onClose }: PricingDetailsPanelProps) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
  }, []);
  return (
    <aside className={styles.panel} aria-label={DETAILS_HEADING}>
      <div className={styles.head}>
        <h3 ref={heading} tabIndex={-1}>
          {DETAILS_HEADING}
        </h3>
        <button
          type="button"
          className={styles.close}
          aria-label="Close the details"
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      <div className={styles.tabs} role="tablist">
        {EXPLAIN_TABS.map((tab) => (
          <button
            key={tab.topic}
            type="button"
            role="tab"
            aria-selected={tab.topic === topic}
            onClick={() => {
              onTopic(tab.topic);
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">
        {topic === 'period' && <PeriodTab />}
        {topic === 'price' && <PriceTab goals={goals} />}
        {topic === 'weights' && <WeightsTab goals={goals} />}
      </div>
      <p className={styles.source}>{SOURCE_LINE}</p>
    </aside>
  );
}
