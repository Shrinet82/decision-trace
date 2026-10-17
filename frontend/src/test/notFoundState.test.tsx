import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AskPage } from '../pages/AskPage';
import { clearAskRuns } from '../hooks/useAskRun';

// The first answer loads the recorded stream fixtures (a dynamic import), which can take a second
const WAIT = { timeout: 5000 };

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
  beforeEach(() => clearAskRuns());

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

    expect(await screen.findByRole('heading', { name: 'No decision found' }, WAIT)).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Evidence path' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Sources' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Still valid/)).not.toBeInTheDocument();
  });

  it('shows an ownership answer without evidence or sources when no decision is primary', async () => {
    renderAsk();
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), {
      target: { value: 'Who owns Elasticsearch?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByText(/Marcus Aurelius/, {}, WAIT)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'No decision found' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Evidence path' })).not.toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Sources' })).not.toBeInTheDocument();
  });

  it('renders answer, evidence path, sources and properties for an answerable question', async () => {
    renderAsk();
    fireEvent.change(screen.getByPlaceholderText(PLACEHOLDER), {
      target: { value: 'What replaced Redis for session storage?' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByRole('region', { name: 'Evidence path' }, WAIT)).toBeInTheDocument();
    expect(await screen.findByRole('region', { name: 'Sources' }, WAIT)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Validity checks')).toBeInTheDocument(), WAIT);
    // The server marks the Keycloak decision as primary; it is active, so the verdict says so.
    expect((await screen.findAllByText('Still valid', {}, WAIT)).length).toBeGreaterThan(0);
  });
});
