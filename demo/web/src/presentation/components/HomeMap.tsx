import { useEffect, useRef } from 'react';
import { circleBounds } from '../../domain/map';
import type { Showcase } from '../../domain/showcase';
import { useGateways } from '../hooks/gateways';
import { basemapStyle } from '../map/basemap-style';
import { homeLayers } from '../map/home-layers';
import { useMapFactory } from '../map/MapContext';
import styles from './Home.module.css';

const REDUCED_MOTION = '(prefers-reduced-motion: reduce)';
const FADE_MS = 300;

/**
 * Home's own map: a picture of the study circle with the hubs and the priced pairs. It is
 * created through the injected factory, never interactive, and reads the basemap file (a
 * static file, not an API call) when the data set has one.
 */
export function HomeMap({ showcase }: { readonly showcase: Showcase }) {
  const factory = useMapFactory();
  const { basemap } = useGateways();
  const containerRef = useRef<HTMLDivElement>(null);
  const { datasetId } = showcase;

  useEffect(() => {
    const container = containerRef.current;
    if (container === null) return undefined;
    const reduced = window.matchMedia(REDUCED_MOTION).matches;
    const declaration = homeLayers(showcase);
    const bounds = circleBounds(showcase.studyCircle.centre, showcase.studyCircle.radiusM);
    const handle = factory(container, {
      style: basemapStyle({ pmtilesUrl: null }),
      fadeDuration: reduced ? 0 : FADE_MS,
      interactive: false,
    });
    // A new style drops what was added: draw again each time one has loaded.
    const stop = handle.onStyleReady(() => {
      for (const [id, source] of Object.entries(declaration.sources)) {
        if (!handle.hasSource(id)) handle.addSource(id, source);
      }
      for (const layer of declaration.layers) {
        if (!handle.hasLayer(layer.id)) handle.addLayer(layer);
      }
      handle.fitBounds(bounds, { animate: false });
    });
    let gone = false;
    void basemap
      .exists(datasetId)
      .catch(() => false)
      .then((exists) => {
        if (!gone && exists) handle.setStyle(basemapStyle({ pmtilesUrl: basemap.url(datasetId) }));
      });
    return () => {
      gone = true;
      stop();
      handle.remove();
    };
  }, [factory, basemap, datasetId, showcase]);

  return <div ref={containerRef} className={styles.map} data-testid="home-map" />;
}
