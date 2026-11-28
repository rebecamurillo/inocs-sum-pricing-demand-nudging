import { FUNDING_STATEMENT, RUN_UNMODIFIED_CONFIRMED, modelSourceLine } from '../../domain/footer';
import markUrl from '../assets/eu-co-funding-mark-placeholder.svg?url';
import styles from './Footer.module.css';

export function Footer() {
  const line = modelSourceLine(RUN_UNMODIFIED_CONFIRMED);
  return (
    <footer className={styles.footer}>
      <img
        className={styles.mark}
        src={markUrl}
        alt="Co-funded by the European Union (placeholder)"
        height="24"
      />
      <span>{FUNDING_STATEMENT}</span>
      <span>
        {line.before}
        {line.authorIsPlaceholder ? (
          <mark className={styles.placeholder} title="The author's name is not supplied yet">
            {line.author}
          </mark>
        ) : (
          line.author
        )}
        {line.after}
      </span>
    </footer>
  );
}
