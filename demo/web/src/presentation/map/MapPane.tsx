import { useEffect, useMemo, useRef } from 'react';
import { circleBounds } from '../../domain/map';
import { useMapBasis } from '../hooks/useMapBasis';
import { basemapStyle } from './basemap-style';
import { useMapFactory, useMapPaneContext } from './MapContext';
import type { MapHandle } from './map-factory';
import styles from './MapPane.module.css';

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
const FADE_MS = 300;

interface MapPaneProps {
  /** False hides the pane (zero width, out of the accessibility tree); the map stays mounted. */
  readonly shown: boolean;
  /** The data set of the open instance version; null shows the most recent one. */
  readonly datasetId: string | null;
}

/** The one map of the Lab: created once, resized and refitted, never re-created. */
export function MapPane({ shown, datasetId }: MapPaneProps) {
  const factory = useMapFactory();
  const { ready, fitTarget, attach, restyling } = useMapPaneContext();
  const basis = useMapBasis(datasetId).data ?? null;
  const paneRef = useRef<HTMLElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<MapHandle | null>(null);
  const appliedUrl = useRef<string | null>(null);

  const presetBounds = useMemo(
    () => (basis === null ? null : circleBounds(basis.dataset.centre, basis.dataset.radiusM)),
    [basis],
  );
  const target = fitTarget ?? presetBounds;
  const targetRef = useRef(target);
  useEffect(() => {
    targetRef.current = target;
  }, [target]);
  const basemapUrl = basis?.basemapUrl ?? null;

  // The map exists for the pane's lifetime. Under reduced motion it does not fade and jumps.
  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return undefined;
    const reduced = window.matchMedia(REDUCED_MOTION).matches;
    const handle = factory(container, {
      style: basemapStyle({ pmtilesUrl: null }),
      fadeDuration: reduced ? 0 : FADE_MS,
    });
    handleRef.current = handle;
    appliedUrl.current = null;
    attach(handle);
    return () => {
      attach(null);
      handleRef.current = null;
      handle.remove();
    };
  }, [factory, attach]);

  // The file arrives after the map: the style then gains the streets and the water.
  useEffect(() => {
    const handle = handleRef.current;
    if (handle === null || basemapUrl === null || appliedUrl.current === basemapUrl) return;
    appliedUrl.current = basemapUrl;
    restyling();
    handle.setStyle(basemapStyle({ pmtilesUrl: basemapUrl }));
  }, [basemapUrl, restyling]);

  // Look at the study circle whenever it changes, and after each style.
  useEffect(() => {
    if (ready === null || target === null) return;
    const reduced = window.matchMedia(REDUCED_MOTION).matches;
    ready.handle.fitBounds(target, { animate: !reduced });
  }, [ready, target]);

  // A pane that changes width or is shown again has a new size: tell the map, refit.
  useEffect(() => {
    const pane = paneRef.current;
    if (pane === null) return undefined;
    const observer = new ResizeObserver(() => {
      const handle = handleRef.current;
      if (handle === null) return;
      handle.resize();
      const current = targetRef.current;
      if (current !== null) {
        const reduced = window.matchMedia(REDUCED_MOTION).matches;
        handle.fitBounds(current, { animate: !reduced });
      }
    });
    observer.observe(pane);
    return () => {
      observer.disconnect();
    };
  }, []);

  return (
    <section ref={paneRef} className={styles.pane} aria-label="Map" hidden={!shown}>
      <div ref={containerRef} className={styles.canvas} />
    </section>
  );
}
