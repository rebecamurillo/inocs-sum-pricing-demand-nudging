import { blockingComponents, componentLabel, type SystemStatus } from '../../domain/system-status';
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

function Loaded({ status }: { status: SystemStatus }) {
  return (
    <>
      <ul className={styles.components}>
        {status.components.map((component) => (
          <li key={component.name} className={styles.component}>
            <span className={styles.name}>{componentLabel(component.name)}</span>
            <span className={component.available ? styles.available : styles.unavailable}>
              {component.available ? 'Available' : 'Unavailable'}
            </span>
            {component.reason !== null && <span className={styles.reason}>{component.reason}</span>}
          </li>
        ))}
      </ul>
      {status.canStartRuns ? (
        <p>New runs can start.</p>
      ) : (
        <>
          <p>New runs cannot start:</p>
          <ul className={styles.reasons}>
            {blockingComponents(status).map((component) => (
              <li key={component.name}>
                {componentLabel(component.name)}: {component.reason}
              </li>
            ))}
          </ul>
        </>
      )}
      {!status.canReadStoredResults && <p>Stored results cannot be read.</p>}
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
