import type { RuleResult } from '../../domain/city-instance';
import { ROUTING_DATE_RULE, RULES_HEADING, ruleLine } from '../../domain/draft-text';
import styles from './DraftForm.module.css';

/** "Rules checked before saving": one line per rule of the last answer, ✓ or ✕ before its text. */
export function RulesBox({ rules }: { rules: readonly RuleResult[] }) {
  // The routing-date rule is written on the Periods line.
  const shown = rules.filter((result) => result.rule !== ROUTING_DATE_RULE);
  return (
    <section className={styles.rulesBox} aria-label={RULES_HEADING}>
      <h3>{RULES_HEADING}</h3>
      <ul className={styles.rules}>
        {shown.map((result) => (
          <li key={result.rule} className={styles.rule} data-passed={String(result.passed)}>
            <span className={styles.mark} aria-hidden="true">
              {result.passed ? '✓' : '✕'}
            </span>
            {ruleLine(result)}
          </li>
        ))}
      </ul>
    </section>
  );
}
