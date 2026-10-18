import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DecisionPage } from '../pages/DecisionPage';
import { PeoplePage } from '../pages/PeoplePage';
import { PersonPage } from '../pages/PersonPage';
import { SystemPage } from '../pages/SystemPage';
import { SystemsPage } from '../pages/SystemsPage';
import { findDecisionDetail } from '../api/mocks';

function renderAt(url: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[url]}>
        <Routes>
          <Route path="/decisions/:code" element={<DecisionPage />} />
          <Route path="/systems" element={<SystemsPage />} />
          <Route path="/systems/:name" element={<SystemPage />} />
          <Route path="/people" element={<PeoplePage />} />
          <Route path="/people/:name" element={<PersonPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Decision page', () => {
  const keycloak = findDecisionDetail('Migrate session storage to embedded Keycloak cache')!;

  it('shows header, lineage, timeline with this decision highlighted, sources and Cypher', async () => {
    renderAt(`/decisions/${keycloak.decision_code}`);
    expect(await screen.findByRole('heading', { level: 1, name: keycloak.title })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Lineage' })).toBeInTheDocument();

    const timeline = screen.getByRole('region', { name: 'System timeline' });
    const current = within(timeline).getByRole('link', { current: 'page' });
    expect(current).toHaveAttribute('href', `/app/decisions/${keycloak.decision_code}`);

    const sources = screen.getByRole('region', { name: 'Sources' });
    expect(within(sources).getByText('TICK-102')).toBeInTheDocument();
    expect(within(sources).getByText(/Alice Vance decided/)).toBeInTheDocument();

    const panel = screen.getByRole('complementary', { name: 'Decision properties' });
    expect(within(panel).getByText('Show Cypher')).toBeInTheDocument();
    const superseded = keycloak.lineage.supersedes[0];
    expect(within(panel).getByRole('link', { name: superseded.decision_code! })).toHaveAttribute(
      'href',
      `/app/decisions/${superseded.decision_code}`
    );
  });

  it('lists lineage nodes as links for keyboard and screen-reader users', async () => {
    renderAt(`/decisions/${keycloak.decision_code}`);
    const list = await screen.findByRole('list', { name: 'Lineage nodes' });
    expect(within(list).getByText(/\(this decision\)/)).toBeInTheDocument();
    expect(within(list).getAllByRole('link').length).toBeGreaterThan(0);
  });

  it('shows a not-found state for an unknown code', async () => {
    renderAt('/decisions/DEC-99');
    expect(await screen.findByRole('heading', { name: 'Decision not found' })).toBeInTheDocument();
  });
});

describe('Systems', () => {
  it('lists systems with the orphaned one flagged', async () => {
    renderAt('/systems');
    const link = await screen.findByRole('link', { name: /Elasticsearch/ });
    expect(within(link).getByText('Orphaned')).toBeInTheDocument();
    expect(within(link).getByText('Left company')).toBeInTheDocument();
  });

  it('filters to orphaned systems', async () => {
    renderAt('/systems?view=orphaned');
    await screen.findByRole('link', { name: /Elasticsearch/ });
    expect(screen.queryByRole('link', { name: /Keycloak/ })).not.toBeInTheDocument();
  });

  it('explains an orphaned system on its page', async () => {
    renderAt('/systems/Elasticsearch');
    expect(await screen.findByRole('heading', { level: 1, name: 'Elasticsearch' })).toBeInTheDocument();
    expect(screen.getByText('No active owner')).toBeInTheDocument();
    expect(screen.getByText(/Marcus Aurelius owns this system but left the company/)).toBeInTheDocument();
    expect(screen.getByText('No decision is recorded for this system.')).toBeInTheDocument();
  });
});

describe('People', () => {
  it('lists people', async () => {
    renderAt('/people');
    expect(await screen.findByRole('link', { name: /Alice Vance/ })).toHaveAttribute('href', '/app/people/Alice%20Vance');
  });

  it("shows a person's decisions and owned systems", async () => {
    renderAt('/people/Alice%20Vance');
    expect(await screen.findByRole('heading', { level: 1, name: 'Alice Vance' })).toBeInTheDocument();
    const decisions = screen.getByRole('region', { name: 'Decisions made' });
    expect(within(decisions).getAllByRole('link').length).toBeGreaterThanOrEqual(3);
    const owned = screen.getByRole('region', { name: 'Systems owned' });
    expect(within(owned).getByRole('link', { name: /Kafka/ })).toHaveAttribute('href', '/app/systems/Kafka');
  });

  it('marks a departed person and their orphaned system', async () => {
    renderAt('/people/Marcus%20Aurelius');
    await screen.findByRole('heading', { level: 1, name: 'Marcus Aurelius' });
    expect(screen.getAllByText('Left company').length).toBeGreaterThan(0);
    const owned = screen.getByRole('region', { name: 'Systems owned' });
    expect(within(owned).getByText('Orphaned')).toBeInTheDocument();
  });
});
