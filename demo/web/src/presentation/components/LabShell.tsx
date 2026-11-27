import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import {
  EMPTY_LAB_VIEW,
  GRIP_STEP,
  MAX_MAP_SHARE,
  MIN_MAP_SHARE,
  clampMapShare,
} from '../../domain/layout';
import { NEW_INSTANCE_ACTION, NO_CITY_DATA } from '../../domain/draft-text';
import { breadcrumb, periodChip } from '../../domain/l1-text';
import { pricingBreadcrumb, pricingVersionName } from '../../domain/pricing-goals-text';
import { pricingVersionId, type PricingVersionState } from '../../domain/pricing-version';
import type { LabRoute } from '../../domain/route';
import { PRICING_VERSIONS_OFF } from '../../domain/run-text';
import {
  instanceLabel,
  missingInstanceVersionLabel,
  nothingAtThisLink,
} from '../../domain/unknown-link';
import { useInstanceMenu, useInstanceView, useNewInstanceBasis } from '../hooks/useCityInstances';
import { useActiveRuns, useEndedRun } from '../hooks/useRuns';
import { useHashRoute } from '../hooks/useHashRoute';
import { useLayoutPreferences } from '../hooks/useLayoutPreferences';
import { usePricingVersion } from '../hooks/usePricingVersions';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { MapPane } from '../map/MapPane';
import { MapProvider } from '../map/MapContext';
import { LoadingCard } from './LoadingCard';
import { Footer } from './Footer';
import { InstanceMenu } from './InstanceMenu';
import { DraftForm } from './DraftForm';
import { InstanceView, type OpenedDraft } from './InstanceView';
import { NewInstanceForm } from './NewInstanceForm';
import { PricingGoalsForm } from './PricingGoalsForm';
import { PricingResultView } from './PricingResultView';
import { PricingRunView } from './PricingRunView';
import { RunLine } from './RunLine';
import styles from './LabShell.module.css';

/** The states of a sealed version whose L-2 is the run's card, not the goals form. */
const SHOWN_AS_RUN: readonly PricingVersionState[] = ['queued', 'running', 'failed', 'cancelled'];

const MENU_WIDTH_PX = 264;
const GRIP_WIDTH_PX = 8;

type MenuChoice = 'instances' | 'compare' | 'traveller';

const choiceLabels: Readonly<Record<MenuChoice, string>> = {
  instances: 'City instances',
  compare: 'Compare versions',
  traveller: 'Trip options and prices',
};

const cardTexts: Readonly<Record<MenuChoice, string>> = {
  instances:
    'No city instance yet. Create one from the Geneva data: it prepares the area, the hubs, the routes and the travellers of one period.',
  compare: 'Compare needs two pricing versions of this city instance.',
  traveller: 'Run a pricing version first.',
};

function unknownLinkSentence(
  route: Exclude<LabRoute, { kind: 'lab' }>,
  instanceName: string | null,
): string {
  // The card names the instance when the menu lists it, else the id as the link writes it.
  return nothingAtThisLink(
    instanceLabel(instanceName, route.instance.instanceId),
    missingInstanceVersionLabel(route.instance.version),
  );
}

function MenuItem({
  choice,
  current,
  onOpen,
  onKeyDown,
}: {
  choice: MenuChoice;
  current: MenuChoice | null;
  onOpen: (choice: MenuChoice) => void;
  onKeyDown: (event: KeyboardEvent<HTMLElement>) => void;
}) {
  return (
    <button
      type="button"
      data-menu-item=""
      className={styles.item}
      aria-current={current === choice ? 'page' : undefined}
      onKeyDown={onKeyDown}
      onClick={() => {
        onOpen(choice);
      }}
    >
      {choiceLabels[choice]}
    </button>
  );
}

/** The empty card's primary: disabled, with the reason, while no city data is imported. */
function NewInstanceAction({ onNew }: { onNew: () => void }) {
  const basis = useNewInstanceBasis();
  const noCityData = basis.data?.dataset === null;
  return (
    <>
      {noCityData && <p className={styles.cardText}>{NO_CITY_DATA}</p>}
      <button
        type="button"
        className={styles.primary}
        disabled={basis.data?.dataset == null}
        onClick={onNew}
      >
        {NEW_INSTANCE_ACTION}
      </button>
    </>
  );
}

export function LabShell() {
  const { route, navigate } = useHashRoute();
  const layout = useLayoutPreferences();
  const [choice, setChoice] = useState<MenuChoice>('instances');
  // The new-instance form before its `POST` is a state of `#/lab`; it ends with any other link.
  const [creating, setCreating] = useState(false);
  // The sentence a draft opens with when the instance already had it: (draft id, sentence).
  const [notice, setNotice] = useState<{ versionId: string; message: string } | null>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  // The poll runs for the views that come; the shell renders nothing from it yet.
  useSystemStatus();

  const menu = useInstanceMenu();
  const { runs: activeRuns } = useActiveRuns();
  const entries = menu.data ?? [];
  // Reset on a change of link, not on the render that follows "+ New": its hash change is
  // still to come when "+ New" is clicked on another link.
  const [seenRoute, setSeenRoute] = useState(route);
  if (seenRoute !== route) {
    setSeenRoute(route);
    if (route.kind !== 'lab') setCreating(false);
  }

  const { menuOpen, mapShown, advancedView, largeText } = layout.preferences;
  const mapShare = layout.mapShare(EMPTY_LAB_VIEW);

  // An instance link is a view only when the menu lists that version; every other link is unknown.
  const linkedRoute =
    route.kind === 'instance' || route.kind === 'pricing' || route.kind === 'result' ? route : null;
  const linkedEntry =
    linkedRoute === null
      ? undefined
      : entries.find((entry) => entry.id === linkedRoute.instance.instanceId);
  const linkedVersion =
    linkedRoute === null
      ? undefined
      : linkedEntry?.versions.find((version) => version.number === linkedRoute.instance.version);
  // L-2 and L-3 have no map: the pane and its grip go, the stored preference stays.
  const pricingRoute = route.kind === 'pricing' || route.kind === 'result' ? route : null;
  const pricingOpen = usePricingVersion(
    pricingRoute !== null && linkedVersion !== undefined
      ? pricingVersionId(linkedVersion.id, pricingRoute.letter)
      : null,
  ).data;
  // The run card stays for a version that gets its result under it: the run list and the
  // version can answer before the card's own run does, and the card opens the result route.
  const [runCardId, setRunCardId] = useState<string | null>(null);
  const showsRunCard =
    route.kind === 'pricing' &&
    pricingOpen != null &&
    (SHOWN_AS_RUN.includes(pricingOpen.state) ||
      (pricingOpen.state === 'result' && runCardId === pricingOpen.id));
  const runCardNow = showsRunCard ? pricingOpen.id : null;
  if (runCardNow !== runCardId) setRunCardId(runCardNow);
  const openVersion =
    linkedEntry !== undefined && linkedVersion !== undefined
      ? { instanceId: linkedEntry.id, versionId: linkedVersion.id }
      : null;
  // A link naming an instance version waits for the menu; only an answered menu says it is unknown.
  const menuPending = linkedRoute !== null && menu.isPending;
  const menuFailed = linkedRoute !== null && menu.isError;
  const unknownLink =
    route.kind === 'lab' || openVersion !== null || menuPending || menuFailed ? null : route;
  const noMap = pricingRoute !== null && openVersion !== null;
  const current: MenuChoice | null =
    openVersion !== null
      ? null
      : unknownLink === null && !menuPending && !menuFailed
        ? choice
        : 'instances';
  // The empty Lab: the card of City instances, with no instance listed.
  const emptyLab =
    menu.data !== undefined &&
    entries.length === 0 &&
    unknownLink === null &&
    current === 'instances';
  const queuedPlaces = new Map(
    activeRuns.flatMap((run) =>
      run.state === 'queued' && run.queuePosition !== null
        ? [[run.subject.id, run.queuePosition + 1] as const]
        : [],
    ),
  );
  const openedView = useInstanceView(openVersion?.versionId ?? null).data ?? null;
  // Held here, not in the run line: the line is unmounted while the menu is closed.
  const openPricingId =
    pricingRoute !== null && openVersion !== null
      ? pricingVersionId(openVersion.versionId, pricingRoute.letter)
      : null;
  const endedRun = useEndedRun([openVersion?.versionId ?? null, openPricingId]);
  const firstPeriod = openedView?.version.periods[0];

  const openResult = (instanceId: string, number: number, letter: string) => {
    setCreating(false);
    navigate({
      kind: 'result',
      instance: { instanceId, version: number },
      letter,
      period: null,
    });
  };

  const openVersionRow = (instanceId: string, number: number) => {
    setCreating(false);
    navigate({ kind: 'instance', instance: { instanceId, version: number }, period: null });
  };

  const openDraft = ({ instanceId, number, message }: OpenedDraft) => {
    setNotice(message === null ? null : { versionId: `${instanceId}.v${String(number)}`, message });
    navigate({ kind: 'instance', instance: { instanceId, version: number }, period: null });
  };

  const startNew = () => {
    setCreating(true);
    if (route.kind !== 'lab') navigate({ kind: 'lab', period: null });
  };

  const open = (next: MenuChoice) => {
    setCreating(false);
    setChoice(next);
    if (route.kind !== 'lab') navigate({ kind: 'lab', period: null });
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    const items = Array.from(
      navRef.current?.querySelectorAll<HTMLElement>('[data-menu-item]') ?? [],
    );
    const at = items.findIndex((item) => item === document.activeElement);
    const step = event.key === 'ArrowDown' ? 1 : -1;
    const next = items[(at + step + items.length) % items.length];
    event.preventDefault();
    next?.focus();
  };

  const setShare = (share: number) => {
    layout.setMapShare(EMPTY_LAB_VIEW, share);
  };

  const onGripKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    // The map is on the right: ← widens it, → narrows it.
    if (event.key === 'ArrowLeft') setShare(mapShare + GRIP_STEP);
    else if (event.key === 'ArrowRight') setShare(mapShare - GRIP_STEP);
    else return;
    event.preventDefault();
  };

  const onGripPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const body = bodyRef.current;
    if (body === null || !event.currentTarget.hasPointerCapture(event.pointerId)) return;
    const box = body.getBoundingClientRect();
    const left = box.left + (menuOpen ? MENU_WIDTH_PX : 0);
    const width = box.right - left;
    if (width <= 0) return;
    setShare(clampMapShare(((box.right - event.clientX) / width) * 100));
  };

  const menuWidth = menuOpen ? `${String(MENU_WIDTH_PX)}px` : '0px';
  const mapVisible = mapShown && !noMap;
  const gripWidth = mapVisible ? `${String(GRIP_WIDTH_PX)}px` : '0px';
  const mapWidth = mapVisible ? `calc((100% - ${menuWidth}) * ${String(mapShare / 100)})` : '0px';

  return (
    <div className={styles.shell}>
      <MapProvider>
        <div
          ref={bodyRef}
          className={styles.body}
          style={{
            gridTemplateColumns: `${menuWidth} minmax(0, 1fr) ${gripWidth} ${mapWidth}`,
          }}
        >
          {menuOpen && (
            <aside className={styles.menu} aria-label="Menu">
              <div className={styles.brand}>
                <span className={styles.logo} aria-hidden="true" />
                <span className={styles.brandName}>SUM</span>
                <span className={styles.brandTitle}>Dynamic pricing · Lab</span>
                <button
                  type="button"
                  className={styles.iconButton}
                  aria-label="Hide the menu"
                  onClick={() => {
                    layout.setMenuOpen(false);
                  }}
                >
                  «
                </button>
              </div>
              <nav ref={navRef} className={styles.nav}>
                <p className={styles.section}>Operator view</p>
                <div className={styles.headRow}>
                  <MenuItem
                    choice="instances"
                    current={current}
                    onOpen={open}
                    onKeyDown={onMenuKeyDown}
                  />
                  <button
                    type="button"
                    data-menu-item=""
                    className={styles.newButton}
                    onKeyDown={onMenuKeyDown}
                    onClick={startNew}
                  >
                    + New
                  </button>
                </div>
                {/* "No instance yet" only once the menu has answered with an empty list. */}
                {menu.data !== undefined && (
                  <InstanceMenu
                    entries={entries}
                    open={openVersion}
                    setupCurrent={openVersion !== null && route.kind === 'instance'}
                    currentLetter={pricingRoute?.letter ?? null}
                    queued={queuedPlaces}
                    onOpenVersion={openVersionRow}
                    onNavigate={navigate}
                    onInstanceDeleted={() => {
                      setCreating(false);
                      navigate({ kind: 'lab', period: null });
                    }}
                    onKeyDown={onMenuKeyDown}
                  />
                )}
                <MenuItem
                  choice="compare"
                  current={current}
                  onOpen={open}
                  onKeyDown={onMenuKeyDown}
                />
                <p className={styles.section}>Traveller view</p>
                <MenuItem
                  choice="traveller"
                  current={current}
                  onOpen={open}
                  onKeyDown={onMenuKeyDown}
                />
              </nav>
              <div className={styles.foot}>
                <button
                  type="button"
                  role="switch"
                  aria-checked={advancedView}
                  className={styles.switch}
                  onClick={() => {
                    layout.setAdvancedView(!advancedView);
                  }}
                >
                  <span className={styles.track} aria-hidden="true" />
                  Advanced view
                </button>
                <RunLine
                  className={styles.runLine}
                  entries={entries}
                  openVersionId={openVersion?.versionId ?? null}
                  openPricingId={openPricingId}
                  onOpen={openVersionRow}
                  onOpenResult={openResult}
                  tracker={endedRun}
                />
              </div>
            </aside>
          )}

          <header className={styles.topBar}>
            {!menuOpen && (
              <button
                type="button"
                className={styles.barButton}
                onClick={() => {
                  layout.setMenuOpen(true);
                }}
              >
                ☰ Menu
              </button>
            )}
            <nav aria-label="Breadcrumb" className={styles.breadcrumb}>
              {linkedEntry !== undefined && linkedVersion !== undefined && openVersion !== null
                ? pricingRoute === null
                  ? breadcrumb(linkedEntry.name, linkedVersion.number)
                  : pricingBreadcrumb(
                      linkedEntry.name,
                      linkedVersion.number,
                      pricingOpen === undefined || pricingOpen === null
                        ? `Version ${pricingRoute.letter}`
                        : pricingVersionName(pricingOpen),
                    )
                : choiceLabels[current ?? 'instances']}
            </nav>
            {firstPeriod !== undefined && (
              <span className={styles.chip}>{periodChip(firstPeriod.label)}</span>
            )}
            {!noMap && (
              <button
                type="button"
                className={styles.barButton}
                onClick={() => {
                  layout.setMapShown(!mapShown);
                }}
              >
                {mapShown ? 'Hide map' : 'Show map'}
              </button>
            )}
            <button
              type="button"
              className={styles.barButton}
              aria-pressed={largeText}
              aria-label="Larger text for a projector"
              onClick={() => {
                layout.setLargeText(!largeText);
              }}
            >
              Aa
            </button>
          </header>

          <main className={styles.card}>
            {openVersion !== null ? (
              // Keyed by version: rows shown on the map and the open table go with the version.
              pricingRoute !== null ? (
                linkedVersion?.state !== 'ready' ? (
                  <p className={styles.cardText}>{PRICING_VERSIONS_OFF}</p>
                ) : pricingRoute.kind === 'pricing' ? (
                  showsRunCard ? (
                    <PricingRunView
                      key={`${openVersion.versionId}.${pricingRoute.letter}`}
                      instanceVersionId={openVersion.versionId}
                      instanceId={openVersion.instanceId}
                      number={linkedVersion.number}
                      letter={pricingRoute.letter}
                      advancedView={advancedView}
                      onNavigate={navigate}
                    />
                  ) : (
                    <PricingGoalsForm
                      key={`${openVersion.versionId}.${pricingRoute.letter}`}
                      instanceVersionId={openVersion.versionId}
                      instanceId={openVersion.instanceId}
                      number={linkedVersion.number}
                      letter={pricingRoute.letter}
                      advancedView={advancedView}
                      onNavigate={navigate}
                    />
                  )
                ) : pricingOpen?.state === 'result' ? (
                  <PricingResultView
                    key={`${openVersion.versionId}.${pricingRoute.letter}`}
                    instanceVersionId={openVersion.versionId}
                    instanceId={openVersion.instanceId}
                    number={linkedVersion.number}
                    letter={pricingRoute.letter}
                    advancedView={advancedView}
                    onNavigate={navigate}
                  />
                ) : pricingOpen?.state === 'draft' ? (
                  <PricingGoalsForm
                    key={`${openVersion.versionId}.${pricingRoute.letter}`}
                    instanceVersionId={openVersion.versionId}
                    instanceId={openVersion.instanceId}
                    number={linkedVersion.number}
                    letter={pricingRoute.letter}
                    advancedView={advancedView}
                    onNavigate={navigate}
                  />
                ) : (
                  // Queued, running, failed, cancelled, still loading or unknown: the L-2 run card.
                  <PricingRunView
                    key={`${openVersion.versionId}.${pricingRoute.letter}`}
                    instanceVersionId={openVersion.versionId}
                    instanceId={openVersion.instanceId}
                    number={linkedVersion.number}
                    letter={pricingRoute.letter}
                    advancedView={advancedView}
                    onNavigate={navigate}
                  />
                )
              ) : linkedVersion?.status === 'draft' ? (
                <DraftForm
                  key={openVersion.versionId}
                  versionId={openVersion.versionId}
                  advancedView={advancedView}
                  onNavigate={navigate}
                  notice={notice?.versionId === openVersion.versionId ? notice.message : null}
                />
              ) : (
                <InstanceView
                  key={openVersion.versionId}
                  versionId={openVersion.versionId}
                  advancedView={advancedView}
                  onOpenDraft={openDraft}
                  onNavigate={navigate}
                />
              )
            ) : creating ? (
              <NewInstanceForm onNavigate={navigate} />
            ) : menuPending ? (
              <LoadingCard />
            ) : menuFailed ? (
              <p className={styles.error}>
                The city instance could not be read: {menu.error.message}
              </p>
            ) : (
              <>
                <p className={styles.cardText}>
                  {unknownLink === null
                    ? cardTexts[current ?? 'instances']
                    : unknownLinkSentence(unknownLink, linkedEntry?.name ?? null)}
                </p>
                {emptyLab && <NewInstanceAction onNew={startNew} />}
              </>
            )}
          </main>

          {mapVisible && (
            <>
              {/* A focusable separator is a widget (WAI-ARIA window splitter); the rules do not know it. */}
              {/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
              <div
                role="separator"
                aria-orientation="vertical"
                aria-label="Drag to make the map wider or narrower"
                aria-valuemin={MIN_MAP_SHARE}
                aria-valuemax={MAX_MAP_SHARE}
                aria-valuenow={mapShare}
                tabIndex={0}
                className={styles.grip}
                onKeyDown={onGripKeyDown}
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture(event.pointerId);
                }}
                onPointerMove={onGripPointerMove}
              />
              {/* eslint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
            </>
          )}

          {/* Hiding the map hides the pane; the map instance stays mounted. */}
          <MapPane shown={mapVisible} datasetId={linkedEntry?.datasetId ?? null} />
        </div>
      </MapProvider>
      <Footer />
    </div>
  );
}
