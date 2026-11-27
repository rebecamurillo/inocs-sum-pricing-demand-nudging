import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import {
  EMPTY_LAB_VIEW,
  GRIP_STEP,
  MAX_MAP_SHARE,
  MIN_MAP_SHARE,
  clampMapShare,
} from '../../domain/layout';
import type { LabRoute } from '../../domain/route';
import {
  instanceLabel,
  missingInstanceVersionLabel,
  nothingAtThisLink,
} from '../../domain/unknown-link';
import { useHashRoute } from '../hooks/useHashRoute';
import { useLayoutPreferences } from '../hooks/useLayoutPreferences';
import { useSystemStatus } from '../hooks/useSystemStatus';
import { MapPane } from '../map/MapPane';
import { MapProvider } from '../map/MapContext';
import { Footer } from './Footer';
import styles from './LabShell.module.css';

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

function unknownLinkSentence(route: Exclude<LabRoute, { kind: 'lab' }>): string {
  // No instance exists yet: the card names the id as the link writes it.
  return nothingAtThisLink(
    instanceLabel(null, route.instance.instanceId),
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
  current: MenuChoice;
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

export function LabShell() {
  const { route, navigate } = useHashRoute();
  const layout = useLayoutPreferences();
  const [choice, setChoice] = useState<MenuChoice>('instances');
  const bodyRef = useRef<HTMLDivElement>(null);
  const navRef = useRef<HTMLElement>(null);
  // The poll runs for the views that come; the shell renders nothing from it yet.
  useSystemStatus();

  const { menuOpen, mapShown, advancedView, largeText } = layout.preferences;
  const mapShare = layout.mapShare(EMPTY_LAB_VIEW);
  const unknownLink = route.kind === 'lab' ? null : route;
  const current: MenuChoice = unknownLink === null ? choice : 'instances';

  const open = (next: MenuChoice) => {
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
  const gripWidth = mapShown ? `${String(GRIP_WIDTH_PX)}px` : '0px';
  const mapWidth = mapShown ? `calc((100% - ${menuWidth}) * ${String(mapShare / 100)})` : '0px';

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
                <MenuItem
                  choice="instances"
                  current={current}
                  onOpen={open}
                  onKeyDown={onMenuKeyDown}
                />
                <p className={styles.hint}>No instance yet</p>
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
                <p className={styles.runLine}>No run in progress</p>
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
              {choiceLabels[current]}
            </nav>
            <button
              type="button"
              className={styles.barButton}
              onClick={() => {
                layout.setMapShown(!mapShown);
              }}
            >
              {mapShown ? 'Hide map' : 'Show map'}
            </button>
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
            <p className={styles.cardText}>
              {unknownLink === null ? cardTexts[current] : unknownLinkSentence(unknownLink)}
            </p>
          </main>

          {mapShown && (
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
          <MapPane shown={mapShown} datasetId={null} />
        </div>
      </MapProvider>
      <Footer />
    </div>
  );
}
