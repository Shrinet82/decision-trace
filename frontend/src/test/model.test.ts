import { describe, it, expect } from 'vitest';
import { buildDecisionRows, countByStatus, evidenceQuoteForSource, healthToStatus, systemsWithDecisions, validityChecks } from '../utils/model';
import { MOCK_DECISION_DETAILS, MOCK_DECISIONS } from '../api/mocks';
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

  it('carries the API decision code and orders codes by decision date', () => {
    expect(rows.every((r) => /^DEC-\d{2}$/.test(r.code ?? ''))).toBe(true);
    expect(new Set(rows.map((r) => r.code)).size).toBe(rows.length);
    const byCode = [...rows].sort((a, b) => a.code!.localeCompare(b.code!));
    const dates = byCode.map((r) => r.decidedOn ?? '');
    expect(dates).toEqual([...dates].sort());
  });

  it('derives relation hints from supersedes/contradicts edges using DEC codes', () => {
    const kafka = rows.find((r) => r.title.startsWith('Adopt Kafka'))!;
    const rabbit = rows.find((r) => r.title.startsWith('Adopt RabbitMQ'))!;
    expect(kafka.status).toBe('conflict');
    expect(kafka.hint?.text).toBe(`conflicts with ${rabbit.code}`);

    const oldSessions = rows.find((r) => r.title.startsWith('Migrate session storage from Postgres'))!;
    expect(oldSessions.status).toBe('superseded');
    expect(oldSessions.hint?.text).toMatch(/^replaced by DEC-\d{2}$/);

    const keycloak = rows.find((r) => r.title === 'Migrate session storage to embedded Keycloak cache')!;
    expect(keycloak.hint?.text).toMatch(/^supersedes DEC-\d{2}$/);
  });

  it('splits list-valued deciders and systems into separate entries', () => {
    const decommission = rows.find((r) => r.title.startsWith('Decommission Snowflake'))!;
    expect(decommission.deciders.length).toBeGreaterThan(1);
    expect(decommission.deciders.every((d) => !d.includes(','))).toBe(true);
    expect(decommission.systems).toEqual(['ClickHouse', 'Snowflake']);
  });

  it('shows a decider-left hint only for stale decisions whose decider departed', () => {
    const stale = buildDecisionRows(
      [
        { ...MOCK_DECISIONS[0], health: 'possibly_stale', decider_departed: true },
        { ...MOCK_DECISIONS[1], health: 'possibly_stale', decider_departed: false },
      ],
      index
    );
    expect(stale[0].hint).toEqual({ text: 'decider left the company', tone: 'stale' });
    expect(stale[1].hint).toEqual({ text: 'needs review', tone: 'stale' });
  });

  it('lists only systems that decisions are about', () => {
    const systems = systemsWithDecisions(index);
    expect(systems.length).toBeGreaterThan(0);
    expect(systems.every((s) => s.decisionCount > 0)).toBe(true);
    expect(systems.map((s) => s.name)).toContain('Kafka');
  });

  it('returns a verbatim evidence quote for a source via based_on', () => {
    const ticket = index.find('TICK-105')!;
    expect(evidenceQuoteForSource(index, ticket.id)).toContain('Kafka');
  });

  it('builds validity checks from detail and graph', () => {
    const kafka = rows.find((r) => r.title.startsWith('Adopt Kafka'))!;
    const checks = validityChecks(MOCK_DECISION_DETAILS[kafka.id]);
    expect(checks.find((c) => c.label.startsWith('Conflicts with'))?.ok).toBe(false);
    expect(checks.find((c) => c.label === 'No newer decision')?.ok).toBe(true);
    expect(checks.find((c) => c.label === 'Decider still on team')?.ok).toBe(true);

    const departed = validityChecks({ ...MOCK_DECISION_DETAILS[kafka.id], decider_departed: true });
    expect(departed.find((c) => c.label === 'Decider left the company')?.ok).toBe(false);
  });
});
