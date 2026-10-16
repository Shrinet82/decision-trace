import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AskPage } from '../pages/AskPage';

function renderAsk() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AskPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const PLACEHOLDER = 'Ask why a decision was made, who owns a system, or what replaced something';

describe('AskPage', () => {
  it('renders the page heading and composer', () => {
    renderAsk();
    expect(screen.getByRole('heading', { level: 1, name: 'Ask' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(PLACEHOLDER)).toBeInTheDocument();
  });

  it('shows the empty state, with no evidence path or sources, for an unanswerable question', async () => {
    renderAsk();
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), {
      target: { value: 'Why did we choose quantum encryption for database backups?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByRole('heading', { name: 'No decision found' })).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Evidence path' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Sources' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Still valid/)).not.toBeInTheDocument();
  });

  it('renders answer, evidence path, sources and properties for an answerable question', async () => {
    renderAsk();
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), {
      target: { value: 'What replaced Redis for session storage?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByRole('region', { name: 'Evidence path' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Sources' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Validity checks')).toBeInTheDocument());
    // The Redis session-storage decision was superseded, so the verdict must say so.
    expect((await screen.findAllByText('Superseded')).length).toBeGreaterThan(0);
  });
});
