import { describe, it, expect } from 'vitest';
import { countByStatus, evidenceQuoteForSource, healthToStatus, ownersWhoLeft, systemsWithDecisions, validityChecks } from '../utils/model';
import { MOCK_DECISION_DETAILS } from '../api/mocks';
import { index, rows } from './fixtures';

describe('decision model (real API fixtures)', () => {
  it('maps health to design status kinds', () => {
    expect(healthToStatus('contradicted')).toBe('conflict');
    expect(healthToStatus('possibly_stale')).toBe('stale');
    expect(healthToStatus('superseded')).toBe('superseded');
    expect(healthToStatus('active')).toBe('active');
  });

  it('counts decisions per status from the API health values', () => {
    expect(rows).toHaveLength(17);
    expect(countByStatus(rows)).toEqual({ active: 12, conflict: 2, stale: 0, superseded: 3 });
  });

  it('derives the source ticket id from based_on edges', () => {
    const kafka = rows.find((r) => r.title.startsWith('Adopt Kafka'))!;
    expect(kafka.ticketId).toBe('TICK-105');
  });

  it('derives relation hints from supersedes/contradicts edges', () => {
    const kafka = rows.find((r) => r.title.startsWith('Adopt Kafka'))!;
    expect(kafka.status).toBe('conflict');
    expect(kafka.hint?.text).toBe('conflicts with TICK-106');

    const oldSessions = rows.find((r) => r.title.startsWith('Migrate session storage from Postgres'))!;
    expect(oldSessions.status).toBe('superseded');
    expect(oldSessions.hint?.text).toMatch(/^replaced by /);

    const keycloak = rows.find((r) => r.title === 'Migrate session storage to embedded Keycloak cache')!;
    expect(keycloak.hint?.text).toMatch(/^supersedes /);
  });

  it('lists only systems that decisions are about', () => {
    const systems = systemsWithDecisions(index);
    expect(systems.length).toBeGreaterThan(0);
    expect(systems.every((s) => s.decisionCount > 0)).toBe(true);
    expect(systems.map((s) => s.name)).toContain('Kafka');
  });

  it('finds owners who left via the owns edge on the decision system', () => {
    // No current decision is about Elasticsearch, so nobody is flagged.
    expect(rows.some((r) => ownersWhoLeft(index, r.id).length > 0)).toBe(false);
    const marcus = index.find('Marcus Aurelius')!;
    expect(marcus.properties.is_active).toBe(false);
  });

  it('returns a verbatim evidence quote for a source via based_on', () => {
    const ticket = index.find('TICK-105')!;
    expect(evidenceQuoteForSource(index, ticket.id)).toContain('Kafka');
  });

  it('builds validity checks from detail and graph', () => {
    const kafka = rows.find((r) => r.title.startsWith('Adopt Kafka'))!;
    const checks = validityChecks(MOCK_DECISION_DETAILS[kafka.id], index);
    expect(checks.find((c) => c.label.startsWith('Conflicts with'))?.ok).toBe(false);
    expect(checks.find((c) => c.label === 'No newer decision')?.ok).toBe(true);
    expect(checks.find((c) => c.label === 'Owner still on team')?.ok).toBe(true);
  });
});
