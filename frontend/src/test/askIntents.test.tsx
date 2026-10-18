import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AskPage } from '../pages/AskPage';
import { SourcesPage } from '../pages/SourcesPage';
import { clearAskRuns } from '../hooks/useAskRun';

const WAIT = { timeout: 5000 };

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<AskPage />} />
          <Route path="/sources" element={<SourcesPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Ask: suggested questions and intents', () => {
  beforeEach(() => clearAskRuns());

  it('lists the five suggested questions under the input', () => {
    renderAt('/');
    const list = screen.getByRole('list', { name: 'Suggested questions' });
    expect(within(list).getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Why did we move sessions to Keycloak?',
      'Do any decisions conflict?',
      "What's affected if we drop Snowflake?",
      'Who knows the most about Kafka?',
      'Which systems have no owner?',
    ]);
  });

  it('renders an impact answer as grouped, linked sections plus the trace', async () => {
    renderAt('/');
    fireEvent.click(screen.getByRole('button', { name: "What's affected if we drop Snowflake?" }));
    const impact = await screen.findByRole('region', { name: 'Impact of changing Snowflake' }, WAIT);
    for (const title of [/^Decisions, /, /^People, /, /^Teams & projects, /, /^Tickets, /]) {
      expect(within(impact).getByRole('region', { name: title })).toBeInTheDocument();
    }
    const decisions = within(impact).getByRole('region', { name: /^Decisions, / });
    expect(within(decisions).getByRole('link', { name: /DEC-13/ })).toHaveAttribute('href', '/app/decisions/DEC-13');
    // Trace: each step, the matched system chip, the Cypher queries and the total time
    const traces = await screen.findAllByRole('region', { name: 'How I found this' }, WAIT);
    const trace = traces[0];
    expect(within(trace).getByRole('link', { name: /Snowflake/ })).toHaveAttribute('href', '/app/systems/Snowflake');
    expect(within(trace).getAllByText(/impact_decisions/).length).toBeGreaterThan(0);
    expect((await within(trace).findByTestId('ask-total-ms', {}, WAIT)).textContent).toMatch(/\d/);
  });

  it('renders an expertise answer as a ranked list with evidence counts', async () => {
    renderAt('/');
    fireEvent.click(screen.getByRole('button', { name: 'Who knows the most about Kafka?' }));
    const list = await screen.findByRole('region', { name: 'People ranked by evidence' }, WAIT);
    const first = within(list).getAllByRole('listitem').find((li) => li.textContent?.includes('Alice Vance'));
    expect(first?.textContent).toMatch(/1 decided · 1 owns · 1 meeting · 1 ticket/);
    expect(within(list).getAllByRole('img')[0]).toHaveAccessibleName(/Alice Vance: .*weighted 9/);
    // No primary decision, so no evidence path
    expect(screen.queryByRole('region', { name: 'Evidence path' })).not.toBeInTheDocument();
  });
});

describe('Sources page', () => {
  it('shows counts, filters by type, and opens a source with its quote highlighted', async () => {
    const user = userEvent.setup();
    renderAt('/sources');
    const counts = await screen.findByRole('list', { name: 'Sources' }, WAIT);
    expect(within(screen.getByLabelText('Source counts')).getByText('Tickets').nextSibling?.textContent).toBe('80');
    await user.click(screen.getByRole('button', { name: 'Meetings', pressed: false }));
    expect(within(counts).getAllByRole('button').length).toBe(12);

    await user.click(screen.getByRole('button', { name: 'All' }));
    await user.type(screen.getByLabelText('Filter sources'), 'TICK-105');
    await user.click(await screen.findByRole('button', { name: /^Ticket TICK-105/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Source' }, WAIT);
    expect(await within(dialog).findByText(/quote highlighted/, {}, WAIT)).toBeInTheDocument();
    expect(dialog.querySelector('mark')?.textContent).toMatch(/Kafka/);
    expect(within(dialog).getByRole('link', { name: /DEC-04/ })).toHaveAttribute('href', '/app/decisions/DEC-04');
  });

  it('opens a company.db record from the URL', async () => {
    renderAt('/sources?open=system%2FElasticsearch');
    const dialog = await screen.findByRole('dialog', { name: 'Source' }, WAIT);
    const fields = await within(dialog).findByRole('region', { name: 'Record fields' }, WAIT);
    expect(fields.textContent).toMatch(/search-engine/);
    expect(within(dialog).getByRole('link', { name: /Marcus Aurelius · owns/ })).toBeInTheDocument();
  });
});
