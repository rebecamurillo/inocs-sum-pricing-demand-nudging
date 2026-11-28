import { afterEach, describe, expect, it, vi } from 'vitest';
import { saveTextFile } from './download';

describe('saveTextFile', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('saves a Blob of the text through a temporary link, then removes both', async () => {
    const created = vi.fn<(blob: Blob) => string>(() => 'blob:file');
    const revoked = vi.fn<(url: string) => void>();
    vi.stubGlobal('URL', { createObjectURL: created, revokeObjectURL: revoked });
    let connectedAtClick = false;
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      connectedAtClick = this.isConnected;
    });

    saveTextFile('table.csv', 'a,b\r\n', 'text/csv;charset=utf-8');

    expect(click).toHaveBeenCalledTimes(1);
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(connectedAtClick).toBe(true);
    expect(link.download).toBe('table.csv');
    expect(link.getAttribute('href')).toBe('blob:file');
    expect(link.isConnected).toBe(false);
    const blob = created.mock.calls[0]?.[0];
    expect(blob?.type).toBe('text/csv;charset=utf-8');
    expect(await blob?.text()).toBe('a,b\r\n');
    expect(revoked).toHaveBeenCalledWith('blob:file');
  });
});
