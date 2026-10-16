import { describe, it, expect } from 'vitest';
import { getMockAskResponse, BENCHMARK_QUESTIONS } from '../api/mocks';
import { ApiError } from '../api/client';

describe('API Client and Mock Fixtures', () => {
  it('loads all 7 benchmark questions and responses', () => {
    expect(BENCHMARK_QUESTIONS).toHaveLength(7);
    for (const item of BENCHMARK_QUESTIONS) {
      expect(item.response).toBeDefined();
      expect(item.response.answer).toBeTypeOf('string');
      expect(item.response.graph_path).toBeDefined();
    }
  });

  it('matches redis session replacement question correctly', () => {
    const res = getMockAskResponse('What replaced Redis for session storage?');
    expect(res.answer).toContain('Keycloak');
    expect(res.citations?.length).toBeGreaterThan(0);
    expect(res.citations?.some((c) => c.id === 'TICK-102')).toBe(true);
    expect(res.citations?.some((c) => c.id === 'TICK-101')).toBe(true);
    expect(res.primary_decision_id).toBeTruthy();
  });

  it('matches prometheus decision question correctly', () => {
    const res = getMockAskResponse('Who decided to adopt Prometheus?');
    expect(res.answer).toContain('Laura Croft');
    expect(res.citations?.some((c) => c.id === 'TICK-109')).toBe(true);
  });

  it('matches vault secret question correctly', () => {
    const res = getMockAskResponse('Why did we choose Vault for secret management?');
    expect(res.answer).toContain('Vault dynamic secrets');
    expect(res.citations?.some((c) => c.id === 'Security Architecture Review')).toBe(true);
  });

  it('handles unanswerable questions with honest refusal', () => {
    const resQuantum = getMockAskResponse('Why did we choose quantum encryption for database backups?');
    expect(resQuantum.citations).toHaveLength(0);
    expect(resQuantum.answer).toContain('not found in the Company Brain');

    const resOracle = getMockAskResponse('What replaced Oracle DB for payment transactions?');
    expect(resOracle.citations).toHaveLength(0);
    expect(resOracle.answer).toContain('not found in the Company Brain');
  });

  it('returns not found fallback for arbitrary unknown questions', () => {
    const res = getMockAskResponse('Some unknown futuristic architecture question?');
    expect(res.answer).toBe('The answer is not found in the Company Brain.');
    expect(res.citations).toHaveLength(0);
  });

  it('instantiates ApiError with status and payload', () => {
    const err = new ApiError('Not found', 404, { detail: 'Missing resource' });
    expect(err.name).toBe('ApiError');
    expect(err.status).toBe(404);
    expect(err.data).toEqual({ detail: 'Missing resource' });
  });
});
