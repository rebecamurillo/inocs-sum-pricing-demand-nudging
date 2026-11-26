import {
  componentLabel,
  stateLabel,
  type ComponentState,
  type SystemStatus,
  type Verdict,
} from '../../domain/system-status';
import { useSystemStatus, type FailureReason } from '../hooks/useSystemStatus';
import styles from './SystemStatusPanel.module.css';

function Loading() {
  return (
    <p role="status" className={styles.loading}>
      <span className={styles.spinner} aria-hidden="true" />
      Reading the system status.
    </p>
  );
}

function Failed({ reason, onRetry }: { reason: FailureReason; onRetry: () => void }) {
  return (
    <div role="alert" className={styles.failure}>
      <p>The system status could not be read.</p>
      <p>
        <strong>{reason.title}.</strong> {reason.detail}
      </p>
      <button type="button" className={styles.action} onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

const stateClasses: Readonly<Record<ComponentState, string>> = {
  available: styles.available ?? '',
  limited: styles.limited ?? '',
  unavailable: styles.unavailable ?? '',
};

function VerdictLine({
  verdict,
  allowed,
  refused,
}: {
  verdict: Verdict;
  allowed: string;
  refused: string;
}) {
  if (verdict.allowed) return <p>{allowed}</p>;
  return (
    <>
      <p>{refused}</p>
      <ul className={styles.reasons}>
        {verdict.reasons.map((blocking) => (
          <li key={blocking.component}>
            {componentLabel(blocking.component)}: {blocking.reason}
          </li>
        ))}
      </ul>
    </>
  );
}

function Loaded({ status }: { status: SystemStatus }) {
  return (
    <>
      <ul className={styles.components}>
        {status.components.map((component) => (
          <li key={component.name} className={styles.component}>
            <span className={styles.name}>{componentLabel(component.name)}</span>
            <span className={stateClasses[component.state]}>{stateLabel(component.state)}</span>
            {component.reason !== null && <span className={styles.reason}>{component.reason}</span>}
          </li>
        ))}
      </ul>
      <VerdictLine
        verdict={status.canBuildInstances}
        allowed="Instance builds can start."
        refused="Instance builds cannot start:"
      />
      <VerdictLine
        verdict={status.canRunPricing}
        allowed="Pricing runs can start."
        refused="Pricing runs cannot start:"
      />
      <VerdictLine
        verdict={status.canSimulate}
        allowed="Simulations can start."
        refused="Simulations cannot start:"
      />
    </>
  );
}

export function SystemStatusPanel() {
  const { state, retry } = useSystemStatus();

  switch (state.kind) {
    case 'loading':
      return <Loading />;
    case 'failed':
      return <Failed reason={state.reason} onRetry={retry} />;
    case 'loaded':
      return <Loaded status={state.status} />;
  }
}
