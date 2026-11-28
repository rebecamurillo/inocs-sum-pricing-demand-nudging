import { useRef, useState } from 'react';
import { NO_CITY_DATA } from '../../domain/draft-text';
import { L1_BRIEF, L1_SENTENCE } from '../../domain/l1-text';
import type { LabRoute } from '../../domain/route';
import { useDraftActions, useNewInstanceBasis } from '../hooks/useCityInstances';
import { LoadingCard } from './LoadingCard';
import { NewInstanceHeader } from './NewInstanceHeader';
import styles from './DraftForm.module.css';

/**
 * The new-instance form before the instance exists: Name, City data and Start from. When Name
 * loses focus (or Enter is pressed) with a name, the instance and its first draft are created
 * and the Lab opens the draft, which shows the four groups.
 */
export function NewInstanceForm({ onNavigate }: { onNavigate: (route: LabRoute) => void }) {
  const basis = useNewInstanceBasis();
  const actions = useDraftActions();
  const [name, setName] = useState('');
  const [startFrom, setStartFrom] = useState('defaults');
  const [note, setNote] = useState<string | null>(null);
  // Enter and the blur that follows it must send one request.
  const sent = useRef(false);

  if (basis.isPending) return <LoadingCard />;
  if (basis.isError) {
    return <p className={styles.error}>The city data could not be read: {basis.error.message}</p>;
  }
  const { dataset, copies } = basis.data;
  if (dataset === null) return <p className={styles.note}>{NO_CITY_DATA}</p>;

  const commit = () => {
    if (name.trim() === '' || sent.current) return;
    sent.current = true;
    setNote(null);
    actions.create
      .mutateAsync({
        name,
        datasetId: dataset.id,
        startFrom:
          startFrom === 'defaults'
            ? { kind: 'package_defaults' }
            : { kind: 'copy', versionId: startFrom.slice('copy:'.length) },
      })
      .then(
        (result) => {
          if (result.kind === 'name_taken') {
            sent.current = false;
            setNote(result.detail);
            return;
          }
          onNavigate({
            kind: 'instance',
            instance: { instanceId: result.version.instanceId, version: result.version.number },
            period: null,
          });
        },
        (error: unknown) => {
          sent.current = false;
          setNote(error instanceof Error ? error.message : String(error));
        },
      );
  };

  return (
    <div className={styles.view}>
      <p className={styles.brief}>
        <span className={styles.rhythm}>{L1_BRIEF}</span>
        <span>{L1_SENTENCE}</span>
      </p>
      <div className={styles.head}>
        <h2 className={styles.name}>New city instance</h2>
      </div>
      <NewInstanceHeader
        name={name}
        onNameChange={(next) => {
          setName(next);
          setNote(null);
        }}
        onNameCommit={commit}
        nameNote={note}
        datasetName={dataset.name}
        copies={copies}
        startFrom={startFrom}
        onStartFrom={setStartFrom}
      />
    </div>
  );
}
