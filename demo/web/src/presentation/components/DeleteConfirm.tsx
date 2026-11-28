import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { Deleted } from '../../application/ports/city-instance-gateway';
import { DELETE_LABEL, KEEP, RUN_ACTIVE_NOTE } from '../../domain/delete-text';
import styles from './DeleteConfirm.module.css';

interface DeleteConfirmProps {
  /** What goes, as a sentence ("Delete Geneva 3 km v1? ..."). */
  readonly question: string;
  /** The confirming button ("Delete v1"). */
  readonly action: string;
  /** Sends the DELETE. */
  readonly remove: () => Promise<Deleted | { readonly kind: string }>;
  /** The note of a refusal, by the kind the DELETE answered; the default is the run-active note. */
  readonly refusalNote?: (kind: string) => string;
  /** Set while the target is, or holds, the home page's showcase: "Delete…" shows it and asks nothing. */
  readonly blockedNote?: string | null;
  /** Called once the DELETE went through: the caller leaves the deleted view. */
  readonly onDeleted: () => void;
  /** Set for a menu row: the arrow keys move between the menu's items. */
  readonly onMenuKeyDown?: (event: KeyboardEvent<HTMLElement>) => void;
}

/**
 * "Delete…" with its confirmation in place: the question, the destructive action and "Keep". A
 * refusal (`run_active`) closes the confirmation and shows its reason as the note of "Delete…".
 * Renders into the flex row that holds it: the trigger, the note and the confirmation.
 */
export function DeleteConfirm({
  question,
  action,
  remove,
  refusalNote = () => RUN_ACTIVE_NOTE,
  blockedNote = null,
  onDeleted,
  onMenuKeyDown,
}: DeleteConfirmProps) {
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const refocus = useRef(false);

  useEffect(() => {
    if (!open && refocus.current) {
      refocus.current = false;
      trigger.current?.focus();
    }
  }, [open]);

  const close = () => {
    refocus.current = true;
    setOpen(false);
  };

  const confirm = () => {
    setPending(true);
    setFailure(null);
    remove().then(
      (answer) => {
        setPending(false);
        if (answer.kind === 'deleted') {
          onDeleted();
          return;
        }
        setNote(refusalNote(answer.kind));
        close();
      },
      (reason: unknown) => {
        setPending(false);
        setFailure(reason instanceof Error ? reason.message : String(reason));
      },
    );
  };

  return (
    <>
      {!open && (
        <button
          ref={trigger}
          type="button"
          className={styles.secondary}
          data-menu-item={onMenuKeyDown === undefined ? undefined : ''}
          onKeyDown={onMenuKeyDown}
          onClick={() => {
            setFailure(null);
            if (blockedNote !== null) {
              setNote(blockedNote);
              return;
            }
            setNote(null);
            setOpen(true);
          }}
        >
          {DELETE_LABEL}
        </button>
      )}
      {!open && note !== null && (
        <p className={styles.note} role="status">
          {note}
        </p>
      )}
      {open && (
        <div className={styles.confirm} role="group" aria-label="Delete">
          <p>{question}</p>
          <div className={styles.buttons}>
            <button type="button" className={styles.danger} disabled={pending} onClick={confirm}>
              {action}
            </button>
            <button type="button" className={styles.secondary} onClick={close}>
              {KEEP}
            </button>
          </div>
          {failure !== null && <p className={styles.error}>{failure}</p>}
        </div>
      )}
    </>
  );
}
