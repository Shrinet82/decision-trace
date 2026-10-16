import { describe, it, expect } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DecisionsPage } from '../pages/DecisionsPage';

function renderPage(url = '/decisions') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <DecisionsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('DecisionsPage', () => {
  it('groups by status in the order Conflict, Active, Superseded with counts', async () => {
    renderPage();
    await screen.findByRole('heading', { name: /Conflict/ });
    const headings = screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent);
    const groupHeadings = headings.filter((t) => /^(Conflict|Possibly stale|Active|Superseded)\d/.test(t ?? ''));
    expect(groupHeadings).toEqual(['Conflict2', 'Active12', 'Superseded3']);
  });

  it('opens a red conflict callout in the peek panel for a conflicting decision', async () => {
    renderPage();
    const group = await screen.findByRole('region', { name: 'Conflict, 2' });
    const first = within(group).getAllByRole('button')[0];
    fireEvent.click(first);
    const peek = screen.getByRole('complementary', { name: 'Selected decision' });
    expect(within(peek).getByText(/^Conflicts with/)).toBeInTheDocument();
    expect(within(peek).getByRole('link', { name: 'Open' })).toHaveAttribute('href', expect.stringContaining('/?q='));
  });

  it('filters by the needs-review tab', async () => {
    renderPage('/decisions?tab=review');
    await screen.findByRole('region', { name: 'Conflict, 2' });
    expect(screen.queryByRole('region', { name: /^Active/ })).not.toBeInTheDocument();
  });

  it('collapses long groups behind a "Show N more" button', async () => {
    renderPage();
    const more = await screen.findByRole('button', { name: 'Show 7 more' });
    fireEvent.click(more);
    expect(screen.queryByRole('button', { name: 'Show 7 more' })).not.toBeInTheDocument();
  });
});
