import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { MOCK_INGEST_ALICE, MOCK_INGEST_KAFKA } from '../api/mocks';
import type { IngestDiff, IngestEvent, SourceRef } from '../api/types';
import { IngestContext } from '../components/ingest/ingestContext';
import { SourceDrawer } from '../components/SourceDrawer';
import { DecisionPage } from '../pages/DecisionPage';
import { DecisionsPage } from '../pages/DecisionsPage';
import { PersonPage } from '../pages/PersonPage';
import { SystemPage } from '../pages/SystemPage';

const diffOf = (events: IngestEvent[]) => {
  const last = events[events.length - 1];
  return (last.event === 'diff' ? last.data : null) as IngestDiff;
};
const KAFKA = diffOf(MOCK_INGEST_KAFKA);
const ALICE = diffOf(MOCK_INGEST_ALICE);

function renderAt(url: string, latestDiff: IngestDiff | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const value = {
    drawerOpen: false,
    tab: 'paste' as const,
    setTab: () => {},
    openDrawer: () => {},
    closeDrawer: () => {},
    latestDiff,
    setLatestDiff: () => {},
  };
  return render(
    <QueryClientProvider client={queryClient}>
      <IngestContext.Provider value={value}>
        <MemoryRouter initialEntries={[url]}>
          <Routes>
            <Route path="/decisions" element={<DecisionsPage />} />
            <Route path="/decisions/:code" element={<DecisionPage />} />
            <Route path="/systems/:name" element={<SystemPage />} />
            <Route path="/people/:name" element={<PersonPage />} />
          </Routes>
        </MemoryRouter>
      </IngestContext.Provider>
    </QueryClientProvider>
  );
}

describe('"Changed just now" marker', () => {
  it('marks a decision whose status the latest ingest changed', async () => {
    renderAt('/decisions/DEC-07', KAFKA);
    await screen.findByRole('heading', { level: 1, name: /RabbitMQ/ });
    expect(screen.getByText('Changed just now')).toBeInTheDocument();
  });

  it('does not mark an untouched decision, or any decision without a diff', async () => {
    const { unmount } = renderAt('/decisions/DEC-11', KAFKA);
    await screen.findByRole('heading', { level: 1, name: /Keycloak/ });
    expect(screen.queryByText('Changed just now')).not.toBeInTheDocument();
    unmount();
    renderAt('/decisions/DEC-07', null);
    await screen.findByRole('heading', { level: 1, name: /RabbitMQ/ });
    expect(screen.queryByText('Changed just now')).not.toBeInTheDocument();
  });

  it('marks changed rows in the decisions list', async () => {
    renderAt('/decisions', KAFKA);
    const row = await screen.findByRole('link', { name: /Adopt RabbitMQ for all event messaging/ });
    expect(within(row).getByText('Changed just now')).toBeInTheDocument();
    // DEC-07 and DEC-04 changed status; DEC-18 is new and not in the (static) mock list
    expect(screen.getAllByText('Changed just now')).toHaveLength(2);
  });

  it('marks a system that became orphaned', async () => {
    renderAt('/systems/Redis', ALICE);
    await screen.findByRole('heading', { level: 1, name: 'Redis' });
    expect(screen.getByText('Changed just now')).toBeInTheDocument();
  });

  it('marks a system a new decision is about', async () => {
    renderAt('/systems/Kafka', KAFKA);
    await screen.findByRole('heading', { level: 1, name: 'Kafka' });
    expect(screen.getByText('Changed just now')).toBeInTheDocument();
  });

  it('marks a person whose record changed, and nobody else', async () => {
    const { unmount } = renderAt('/people/Alice%20Vance', ALICE);
    await screen.findByRole('heading', { level: 1, name: 'Alice Vance' });
    expect(screen.getByText('Changed just now')).toBeInTheDocument();
    unmount();
    renderAt('/people/Bob%20Martin', ALICE);
    await screen.findByRole('heading', { level: 1, name: 'Bob Martin' });
    expect(screen.queryByText('Changed just now')).not.toBeInTheDocument();
  });
});

describe('Source drawer', () => {
  const source: SourceRef = {
    type: 'ticket',
    id: 'TICK-200',
    title: 'Event bus',
    date: '2026-03-04',
    quote: 'use kafka for all event messaging',
    text: 'Background.\nProposal: Use Kafka for all event messaging across services. Thanks.',
  };

  it('shows the full text with the quote highlighted (case-insensitive)', () => {
    render(<SourceDrawer source={source} onClose={() => {}} />);
    const dialog = screen.getByRole('dialog', { name: 'Source' });
    expect(within(dialog).getByText('TICK-200')).toBeInTheDocument();
    const mark = dialog.querySelector('mark');
    expect(mark).toHaveTextContent('Use Kafka for all event messaging');
    expect(within(dialog).getByTestId('source-text')).toHaveTextContent(
      'Background. Proposal: Use Kafka for all event messaging across services. Thanks.'
    );
    expect(within(dialog).queryByText(/not found verbatim/)).not.toBeInTheDocument();
  });

  it('shows the quote above the text when it is not in the text', () => {
    render(<SourceDrawer source={{ ...source, quote: 'Adopt RabbitMQ' }} onClose={() => {}} />);
    const dialog = screen.getByRole('dialog', { name: 'Source' });
    expect(dialog.querySelector('mark')).toBeNull();
    expect(within(dialog).getByText(/not found verbatim/)).toBeInTheDocument();
    expect(within(dialog).getByText('“Adopt RabbitMQ”')).toBeInTheDocument();
  });

  it('opens from a decision source card and returns focus on Escape', async () => {
    const user = userEvent.setup();
    const { unmount } = renderAt('/decisions/DEC-11', null);
    const button = await screen.findByRole('button', { name: 'View source TICK-102' });
    await user.click(button);
    const dialog = screen.getByRole('dialog', { name: 'Source' });
    expect(dialog.querySelector('mark')).toHaveTextContent(
      'Alice Vance decided: Migrate session storage to embedded Keycloak cache.'
    );
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog', { name: 'Source' })).not.toBeInTheDocument();
    expect(button).toHaveFocus();
    unmount();
  });
});
