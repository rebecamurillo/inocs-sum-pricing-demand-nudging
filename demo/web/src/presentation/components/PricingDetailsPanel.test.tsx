import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { samplePricingGoals } from '../../application/ports/fake-pricing-gateway';
import type { ExplainTopic } from '../../domain/pricing-goals-text';
import type { PricingGoals } from '../../domain/pricing-version';
import { PricingDetailsPanel } from './PricingDetailsPanel';

const SOURCE =
  "Read from the model's package, unmodified: it maximises ridership weight × riders + price × riders − cost × riders + balance weight × balance effect, counted on public transport + bike trips.";

function mount(topic: ExplainTopic, goals: PricingGoals = samplePricingGoals) {
  const onTopic = vi.fn();
  const onClose = vi.fn();
  render(<PricingDetailsPanel topic={topic} goals={goals} onTopic={onTopic} onClose={onClose} />);
  return { onTopic, onClose };
}

describe('PricingDetailsPanel', () => {
  it('has the three tabs, the open one selected, and the source line under every tab', () => {
    for (const topic of ['period', 'price', 'weights'] as const) {
      const { unmount } = render(
        <PricingDetailsPanel
          topic={topic}
          goals={samplePricingGoals}
          onTopic={vi.fn()}
          onClose={vi.fn()}
        />,
      );
      const tabs = screen.getAllByRole('tab');
      expect(tabs.map((tab) => tab.textContent)).toEqual([
        '1 Period',
        '2 Cost and price',
        '3 Weights',
      ]);
      expect(tabs.filter((tab) => tab.getAttribute('aria-selected') === 'true')).toHaveLength(1);
      expect(screen.getByText(SOURCE)).toBeInTheDocument();
      unmount();
    }
    expect(screen.queryByText(SOURCE)).not.toBeInTheDocument();
  });

  it('changes tab and closes through its callbacks', async () => {
    const { onTopic, onClose } = mount('period');

    await userEvent.click(screen.getByRole('tab', { name: '2 Cost and price' }));
    await userEvent.click(screen.getByRole('button', { name: 'Close the details' }));

    expect(onTopic).toHaveBeenCalledWith('price');
    expect(onClose).toHaveBeenCalled();
  });

  it('writes the period tab: the prices hold, what the instance holds, the next version', () => {
    mount('period');

    expect(
      screen.getByText(
        'The model sets a price for each bike option it offers, and those prices hold for the whole period: Monday 08:00–09:00.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/one run per period, each starting with the bikes the period before left/),
    ).toBeInTheDocument();
    expect(screen.getByText('NEXT VERSION')).toBeInTheDocument();
  });

  it('draws the number line with its three sections, and hatches the loss only under the cost', () => {
    const { unmount } = render(
      <PricingDetailsPanel
        topic="price"
        goals={{ ...samplePricingGoals, lowest_price_chf: 0.4 }}
        onTopic={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText('Lowest price against cost')).toBeInTheDocument();
    expect(screen.getByText('Profit is not typed in')).toBeInTheDocument();
    expect(screen.getByText('The highest price is not typed in either')).toBeInTheDocument();
    expect(screen.getByText('cost 0.60')).toBeInTheDocument();
    expect(screen.getByText('lowest price 0.40')).toBeInTheDocument();
    expect(screen.getByTestId('loss')).toBeInTheDocument();
    expect(screen.getByText(/Hatched: rides sold under their cost\./)).toBeInTheDocument();
    unmount();

    mount('price');
    expect(screen.queryByTestId('loss')).not.toBeInTheDocument();
    expect(screen.queryByText(/Hatched/)).not.toBeInTheDocument();
  });

  it('computes the example ride from the form values and hatches a negative margin', () => {
    mount('weights', { ...samplePricingGoals, cost_bike_chf: 2 });

    const panel = screen.getByRole('complementary');
    expect(within(panel).getByText('Profit: price − cost')).toBeInTheDocument();
    expect(within(panel).getByText('−0.60')).toBeInTheDocument();
    expect(within(panel).getByText('+ 8.00')).toBeInTheDocument();
    expect(within(panel).getByText('+ 0.20')).toBeInTheDocument();
    expect(within(panel).getByText('7.60')).toBeInTheDocument();
    expect(within(panel).getByText(/^On this ride, ridership counts most/)).toBeInTheDocument();
    expect(within(panel).getByText('Reading a weight')).toBeInTheDocument();
    expect(panel.querySelector('[data-negative="true"]')).not.toBeNull();
  });
});
