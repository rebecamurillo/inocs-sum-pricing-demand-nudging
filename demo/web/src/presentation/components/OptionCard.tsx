import { useId, useState } from 'react';
import {
  durationLine,
  legStrip,
  makeUp,
  otherBikeOptionLine,
  otherBikeOptionsLabel,
} from '../../domain/trip-options';
import { legLine } from '../../domain/trip-route';
import { OPTION_CARDS, priceText, type QuotedOption } from '../../domain/traveller';
import styles from './TravellerView.module.css';

interface OptionCardProps {
  readonly card: (typeof OPTION_CARDS)[number];
  readonly option: QuotedOption;
  /** The other offered PT + bike options; empty on the other cards. */
  readonly others: readonly QuotedOption[];
  /** The price this card showed for the version before, struck through. */
  readonly before: number | undefined;
  /** The card whose legs are listed and whose route is drawn. */
  readonly selected: boolean;
  readonly onSelect: () => void;
}

/** One mode's card: the most taken option, its leg strip and make-up, and the other bike options. */
export function OptionCard({ card, option, others, before, selected, onSelect }: OptionCardProps) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const made = makeUp(option);
  return (
    <li className={styles.card} data-mode={card.mode} data-testid={`card-${card.mode}`}>
      <button type="button" className={styles.cardHead} aria-pressed={selected} onClick={onSelect}>
        <span aria-hidden="true">{card.icon}</span>
        <span>{card.label}</span>
        <span className={styles.price} data-testid={`price-${card.mode}`}>
          {priceText(option.price)}
          {before !== undefined && <del>{priceText(before)}</del>}
        </span>
      </button>
      {selected && (
        <ol className={styles.legs} aria-label="Legs">
          {option.legs.map((leg, at) => (
            // Legs have no id and may repeat; the position is their identity.
            <li key={at}>{legLine(leg)}</li>
          ))}
        </ol>
      )}
      <p className={styles.duration}>{durationLine(option)}</p>
      <div className={styles.strip} aria-hidden="true">
        {legStrip(option.legs).map((segment, at) => (
          <span
            // Legs have no id and may repeat a kind; the position is their identity.
            key={at}
            style={{ flexGrow: segment.share, backgroundColor: segment.colour }}
          />
        ))}
      </div>
      <p className={styles.makeUp}>
        {made.parts.map((part) =>
          part.bold ? <strong key={part.text}>{part.text}</strong> : part.text,
        )}
        {made.tag !== null && <span className={styles.modelTag}>{made.tag}</span>}
      </p>
      {others.length > 0 && (
        <>
          <button
            type="button"
            className={styles.others}
            aria-expanded={open}
            aria-controls={listId}
            onClick={() => {
              setOpen((now) => !now);
            }}
          >
            {otherBikeOptionsLabel(others.length)}
          </button>
          {open && (
            <ul className={styles.otherList} id={listId}>
              {others.map((other) => {
                const line = otherBikeOptionLine(other);
                return (
                  <li key={other.arcId}>
                    <span>{line.legs}</span>
                    <span>{line.duration}</span>
                    <span>{line.price}</span>
                  </li>
                );
              })}
            </ul>
          )}
        </>
      )}
    </li>
  );
}
