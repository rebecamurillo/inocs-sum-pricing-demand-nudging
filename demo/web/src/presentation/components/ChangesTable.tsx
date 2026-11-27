import type { BuildPlan, ParameterChange } from '../../domain/city-instance';
import { causeRows, changeRows } from '../../domain/draft-text';
import { versionTag } from '../../domain/l1-text';
import styles from './DraftForm.module.css';

/** "What v2 changes": a row per changed value and a full-width row per cause that is not a value. */
export function ChangesTable({
  changes,
  plan,
  draftNumber,
  basedNumber,
  bikeStationsFetchedAt,
}: {
  changes: readonly ParameterChange[];
  plan: BuildPlan;
  draftNumber: number;
  basedNumber: number;
  bikeStationsFetchedAt: string;
}) {
  const rows = changeRows(changes);
  const causes = causeRows(plan, basedNumber, bikeStationsFetchedAt);
  if (rows.length === 0 && causes.length === 0) return null;
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th scope="col">What {versionTag(draftNumber)} changes</th>
          <th scope="col">{versionTag(basedNumber)}</th>
          <th scope="col">{versionTag(draftNumber)}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.name}>
            <td>{row.name}</td>
            <td>{row.before}</td>
            <td>
              <b>{row.after}</b>
            </td>
          </tr>
        ))}
        {causes.map((cause) => (
          <tr key={cause}>
            <td colSpan={3}>{cause}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
