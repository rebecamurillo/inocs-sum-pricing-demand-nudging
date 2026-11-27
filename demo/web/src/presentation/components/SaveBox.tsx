import type { BuildPlan } from '../../domain/city-instance';
import { measuredSentence, saveBox } from '../../domain/draft-text';
import styles from './DraftForm.module.css';

/** What saving does: the new number, what stays, what is rebuilt and what that costs. */
export function SaveBox({
  name,
  draftNumber,
  basedNumber,
  pricingVersions,
  plan,
}: {
  name: string;
  draftNumber: number;
  basedNumber: number;
  pricingVersions: number;
  plan: BuildPlan;
}) {
  const sentence = [
    saveBox(name, draftNumber, basedNumber, pricingVersions, plan),
    measuredSentence(plan),
  ]
    .filter((part) => part !== null)
    .join(' ');
  return (
    <div className={styles.saveBox}>
      <p>{sentence}</p>
    </div>
  );
}
