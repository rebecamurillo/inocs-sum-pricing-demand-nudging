import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LoadingCard } from './LoadingCard';

describe('LoadingCard', () => {
  it('shows the skeleton alone on a first load', () => {
    render(<LoadingCard />);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    expect(screen.queryByTestId('previous-render')).not.toBeInTheDocument();
  });

  it('keeps the previous render under the skeleton on a reload', () => {
    render(<LoadingCard previous={<p>Version B result</p>} />);

    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument();
    const previous = screen.getByTestId('previous-render');
    expect(previous).toHaveTextContent('Version B result');
    expect(previous).toHaveAttribute('aria-hidden', 'true');
    expect(previous.className).toContain('previous');
  });
});
