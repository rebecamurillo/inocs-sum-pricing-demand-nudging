import { describe, expect, it } from 'vitest';
import { basemapStyle, MAP_COLOURS } from './basemap-style';

describe('basemapStyle', () => {
  it('is the ground colour alone without a file', () => {
    const style = basemapStyle({ pmtilesUrl: null });

    expect(style.sources).toEqual({});
    expect(style.layers).toEqual([
      { id: 'background', type: 'background', paint: { 'background-color': '#e4e5e2' } },
    ]);
  });

  it('draws water, land cover and streets from the OpenMapTiles layers with a file', () => {
    const style = basemapStyle({ pmtilesUrl: '/basemap/d1.pmtiles' });

    expect(style.sources).toEqual({
      basemap: { type: 'vector', url: 'pmtiles:///basemap/d1.pmtiles' },
    });
    expect(
      style.layers.filter((layer) => layer.source !== undefined).map((l) => l['source-layer']),
    ).toEqual(['landcover', 'water', 'transportation']);
    const paint = (id: string) => style.layers.find((layer) => layer.id === id)?.paint;
    expect(paint('background')).toEqual({ 'background-color': '#e4e5e2' });
    expect(paint('water')).toEqual({ 'fill-color': '#d4dbdc' });
    expect(paint('transportation')?.['line-color']).toBe('#fafaf9');
  });

  it.each([null, '/basemap/d1.pmtiles'])(
    'has no symbol layer, no glyphs, no sprite and no remote address (%s)',
    (pmtilesUrl) => {
      const style = basemapStyle({ pmtilesUrl });
      const text = JSON.stringify(style);

      expect(style.layers.some((layer) => (layer.type as string) === 'symbol')).toBe(false);
      expect(style).not.toHaveProperty('glyphs');
      expect(style).not.toHaveProperty('sprite');
      expect(text).not.toMatch(/https?:/);
    },
  );

  it('uses only the identity tokens for colours', () => {
    const colours = JSON.stringify(basemapStyle({ pmtilesUrl: '/x.pmtiles' })).match(
      /#[0-9a-f]{6}/g,
    );

    expect(new Set(colours)).toEqual(
      new Set([MAP_COLOURS.ground, MAP_COLOURS.water, MAP_COLOURS.street]),
    );
  });
});
