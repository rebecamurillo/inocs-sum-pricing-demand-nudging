import { MODEL_TAG, SIMULATION_TAG } from '../../domain/result-text';
import styles from './SourceTag.module.css';

/** The tag that says where a figure comes from: the simulation or the pricing model. */
export function SourceTag({ kind }: { kind: 'simulation' | 'model' }) {
  return (
    <span className={styles.tag} data-kind={kind}>
      {kind === 'simulation' ? SIMULATION_TAG : MODEL_TAG}
    </span>
  );
}
