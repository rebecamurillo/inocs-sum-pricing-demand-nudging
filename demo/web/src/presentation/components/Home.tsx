import { useRef } from 'react';
import { limitsLine } from '../../domain/home-text';
import { RUN_UNMODIFIED_CONFIRMED } from '../../domain/footer';
import { useHashRoute } from '../hooks/useHashRoute';
import { Footer } from './Footer';
import styles from './Home.module.css';
import { HomeVisual } from './HomeVisual';

const POINTS = [
  {
    title: 'The problem',
    text: 'For each trip, people compare time, price and changes. Too often the car wins, and a flat bike price is the same on every trip.',
  },
  {
    title: 'The idea',
    text: "You say what matters: more riders, the operator's profit, bikes where they are needed. The model chooses a price for each trip, lower where a bike can replace a car. Nobody is forced: travellers still choose.",
  },
  {
    title: 'A familiar lever, a different goal',
    text: 'Plane tickets move with demand to fill the plane. Here the price moves with the trip, to take cars off the street.',
  },
] as const;

export function Home() {
  const { navigate } = useHashRoute();
  const section2 = useRef<HTMLElement>(null);
  const limits = limitsLine(RUN_UNMODIFIED_CONFIRMED);

  const tryIt = () => {
    // The hash stays: the router owns it. Smooth scrolling is off under reduced motion.
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    section2.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={[styles.wrap, styles.headerRow].join(' ')}>
          <span className={styles.logo} aria-hidden="true" />
          <span className={styles.logoName}>SUM</span>
          <b className={styles.headerTitle}>Dynamic pricing</b>
          <button type="button" className={styles.tryIt} onClick={tryIt}>
            Try it
          </button>
        </div>
      </header>
      <main>
        <section className={styles.hero} aria-label="Understand it">
          <div className={[styles.wrap, styles.heroGrid].join(' ')}>
            <div>
              <p className={styles.eyebrow}>For cities and public transport operators</p>
              <h1 className={styles.title}>
                Price shared bikes by the trip, and fewer people take the car.
              </h1>
              <p className={styles.lead}>
                A research model from the SUM project sets the bike price of each trip, to nudge
                travellers from the car to shared bikes and public transport.
              </p>
              <ol className={styles.points}>
                {POINTS.map((point, at) => (
                  <li key={point.title}>
                    <span className={styles.number} aria-hidden="true">
                      {at + 1}
                    </span>
                    <div>
                      <b>{point.title}</b>
                      <span>{point.text}</span>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
            <HomeVisual />
          </div>
        </section>
        <section ref={section2} className={styles.try} aria-labelledby="home-try">
          <div className={styles.wrap}>
            <h2 id="home-try" className={styles.eyebrow}>
              Try it
            </h2>
            <p className={styles.sectionTitle}>Two ways in. Choose by what you want to do.</p>
            <div className={styles.cards}>
              <article className={[styles.card, styles.play].join(' ')}>
                <p className={styles.who}>5 minutes · for everyone</p>
                <h3>Play: take the operator&apos;s seat</h3>
                <p className={styles.cardText}>
                  One mission: get travellers out of their cars without losing revenue. Three
                  choices, three tries, then watch your prices at work over one day.
                </p>
                <span className={styles.soon}>Coming after the proof of concept</span>
                <button
                  type="button"
                  className={styles.secondary}
                  aria-disabled="true"
                  title="Play is designed and is built after the proof of concept."
                >
                  Play the game →
                </button>
              </article>
              <article className={[styles.card, styles.lab].join(' ')}>
                <p className={styles.who}>For analysts and researchers</p>
                <h3>Lab: run the model yourself</h3>
                <p className={styles.cardText}>
                  Prepare a city instance, set the pricing goals, run the model live for one morning
                  hour, then compare versions and the price of any trip.
                </p>
                <button
                  type="button"
                  className={styles.primary}
                  data-primary="true"
                  onClick={() => {
                    navigate({ kind: 'lab', period: null });
                  }}
                >
                  Open the Lab →
                </button>
              </article>
            </div>
            <p className={styles.fine} data-testid="limits-line">
              {limits.before}
              {limits.authorIsPlaceholder ? (
                <mark className={styles.placeholder} title="The author's name is not supplied yet">
                  {limits.author}
                </mark>
              ) : (
                limits.author
              )}
              {limits.after}
            </p>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}
