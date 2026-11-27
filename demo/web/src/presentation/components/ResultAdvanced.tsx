import { useId, type ReactNode } from 'react';
import {
  ABOUT_HEADING,
  ADVANCED_TITLE,
  BIKE_RIDE_SENTENCE,
  COEFFICIENTS_HEADING,
  COMPUTED_FROM_FLOWS,
  EARLIER_HEADING,
  OBJECTIVE_HEADING,
  PACKAGE_SUMMARY_HEADING,
  PARAMETERS_HEADING,
  SIMULATION_HEADING,
  SOLVER_HEADING,
  aboutRows,
  coefficientRows,
  coefficientsText,
  earlierSimulations,
  hasObjectiveTerms,
  objectiveRows,
  packageSummaryRows,
  parameterRows,
  ruleLine,
  simulationRows,
  solverRows,
  type AdvancedRow,
} from '../../domain/advanced-text';
import { bikeOptionsOffered } from '../../domain/hub-pair-table';
import type { HubPairResult, PricingResult, StoredSimulation } from '../../domain/pricing-result';
import { SourceTag } from './SourceTag';
import styles from './ResultAdvanced.module.css';

interface ResultAdvancedProps {
  readonly result: PricingResult;
  readonly flatPrice: number;
  /** The instance's hub pairs with routes; null while the instance view is not read. */
  readonly hubPairs: number | null;
  readonly hubPairResults: readonly HubPairResult[] | null;
  /** Every stored simulation of the version; null while not read. */
  readonly stored: readonly StoredSimulation[] | null;
}

function Rows({ rows }: { readonly rows: readonly AdvancedRow[] }) {
  return (
    <table className={styles.table}>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <th scope="row">
              {row.code === true ? <code className={styles.mono}>{row.label}</code> : row.label}
            </th>
            <td>
              {row.value}
              {row.tag !== undefined && (
                <>
                  {' '}
                  <SourceTag kind={row.tag} />
                </>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Group({
  heading,
  tag,
  children,
}: {
  readonly heading: string;
  readonly tag?: 'model' | 'simulation';
  readonly children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section className={styles.group} aria-labelledby={headingId}>
      <div className={styles.head}>
        {tag !== undefined && <SourceTag kind={tag} />}
        <h3 id={headingId} className={styles.heading}>
          {heading}
        </h3>
      </div>
      {children}
    </section>
  );
}

/** The Advanced view of L-3: the solver's numbers, the rule, the package's summary, the inputs and the provenance. */
export function ResultAdvanced({
  result,
  flatPrice,
  hubPairs,
  hubPairResults,
  stored,
}: ResultAdvancedProps) {
  const { advanced, simulations, provenance } = result;
  const objective = objectiveRows(advanced);
  const earlier = earlierSimulations(stored ?? []);
  return (
    <section className={styles.advanced} aria-labelledby="advanced-view-title">
      <h2 id="advanced-view-title" className={styles.title}>
        {ADVANCED_TITLE}
      </h2>
      <Group heading={OBJECTIVE_HEADING}>
        <Rows rows={objective} />
        {hasObjectiveTerms(objective) && <p className={styles.note}>{COMPUTED_FROM_FLOWS}</p>}
      </Group>
      <Group heading={SOLVER_HEADING} tag="model">
        <Rows
          rows={solverRows(
            advanced,
            hubPairs,
            hubPairResults === null ? null : bikeOptionsOffered(hubPairResults),
          )}
        />
      </Group>
      <Group heading={SIMULATION_HEADING} tag="simulation">
        <p className={styles.note}>{ruleLine(simulations.modelPrices)}</p>
        <Rows rows={simulationRows(simulations.modelPrices, simulations.flat)} />
        <p className={styles.note}>{BIKE_RIDE_SENTENCE}</p>
        {earlier.length > 0 && (
          <>
            <h4 className={styles.heading}>{EARLIER_HEADING}</h4>
            <ul className={styles.list}>
              {earlier.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </>
        )}
      </Group>
      <Group heading={PACKAGE_SUMMARY_HEADING}>
        <Rows rows={packageSummaryRows(advanced)} />
      </Group>
      <Group heading={PARAMETERS_HEADING}>
        <Rows rows={parameterRows(advanced, flatPrice)} />
      </Group>
      <Group heading={COEFFICIENTS_HEADING}>
        <p className={styles.note}>{coefficientsText(result.coefficients)}</p>
        {result.coefficients !== null && <Rows rows={coefficientRows(result.coefficients)} />}
      </Group>
      <Group heading={ABOUT_HEADING}>
        <Rows rows={aboutRows(provenance, advanced.solverStatusName)} />
      </Group>
    </section>
  );
}
