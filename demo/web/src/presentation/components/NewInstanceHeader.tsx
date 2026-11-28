import {
  ANOTHER_CITY,
  ANOTHER_CITY_SENTENCE,
  START_FROM_DEFAULTS,
  copyOption,
} from '../../domain/draft-text';
import styles from './DraftForm.module.css';

export interface StartFromOption {
  readonly value: string;
  readonly label: string;
}

interface NewInstanceHeaderProps {
  readonly name: string;
  /** Absent once the instance exists: the name is then read-only. */
  readonly onNameChange?: (name: string) => void;
  readonly onNameCommit?: () => void;
  readonly nameNote: string | null;
  readonly datasetName: string;
  readonly copies: readonly {
    readonly versionId: string;
    readonly name: string;
    readonly number: number;
  }[];
  /** `defaults`, or `copy:{version id}`. */
  readonly startFrom: string;
  readonly onStartFrom?: (value: string) => void;
}

/** The first three fields of the new-instance form: Name, City data, Start from. */
export function NewInstanceHeader({
  name,
  onNameChange,
  onNameCommit,
  nameNote,
  datasetName,
  copies,
  startFrom,
  onStartFrom,
}: NewInstanceHeaderProps) {
  return (
    <div>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="new-instance-name">
          Name
        </label>
        <div className={styles.inputs}>
          <input
            id="new-instance-name"
            className={styles.nameInput}
            value={name}
            readOnly={onNameChange === undefined}
            aria-invalid={nameNote !== null}
            aria-describedby={nameNote === null ? undefined : 'new-instance-name-note'}
            onChange={(event) => {
              onNameChange?.(event.target.value);
            }}
            onBlur={() => {
              onNameCommit?.();
            }}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onNameCommit?.();
            }}
          />
        </div>
        {nameNote !== null && (
          <p id="new-instance-name-note" className={styles.fieldNote} role="alert">
            {nameNote}
          </p>
        )}
      </div>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="new-instance-city">
          City data
        </label>
        <div className={styles.inputs}>
          <select
            id="new-instance-city"
            className={styles.select}
            value="dataset"
            disabled={onNameChange === undefined}
            onChange={() => undefined}
          >
            <option value="dataset">{datasetName}</option>
            <option value="another" disabled>
              {ANOTHER_CITY}
            </option>
          </select>
        </div>
        <p className={styles.sentence}>{ANOTHER_CITY_SENTENCE}</p>
      </div>
      <div className={styles.field}>
        <label className={styles.label} htmlFor="new-instance-start">
          Start from
        </label>
        <div className={styles.inputs}>
          <select
            id="new-instance-start"
            className={styles.select}
            value={startFrom}
            onChange={(event) => {
              onStartFrom?.(event.target.value);
            }}
          >
            <option value="defaults">{START_FROM_DEFAULTS}</option>
            {copies.map((copy) => (
              <option key={copy.versionId} value={`copy:${copy.versionId}`}>
                {copyOption(copy.name, copy.number)}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
