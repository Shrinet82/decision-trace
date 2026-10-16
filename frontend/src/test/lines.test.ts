import { describe, it, expect } from 'vitest';
import { getSystemLine, CATEGORY_LINES } from '../config/lines';

describe('System category mappings', () => {
  it('maps messaging systems', () => {
    expect(getSystemLine('Kafka').id).toBe('messaging');
    expect(getSystemLine('rabbitmq').color).toBe('#C72C7A');
  });

  it('maps identity and security systems', () => {
    expect(getSystemLine('Keycloak').id).toBe('identity');
    expect(getSystemLine('Vault').color).toBe('#12807A');
  });

  it('maps data systems', () => {
    for (const name of ['Postgres', 'Redis', 'ClickHouse', 'Snowflake', 'Elasticsearch']) {
      expect(getSystemLine(name).id).toBe('data');
    }
  });

  it('maps observability systems', () => {
    expect(getSystemLine('Prometheus').id).toBe('observability');
    expect(getSystemLine('Datadog').color).toBe('#C98A00');
  });

  it('resolves composite system names by their first known part', () => {
    expect(getSystemLine('Snowflake, ClickHouse').id).toBe('data');
  });

  it('falls back to platform for unknown or missing systems', () => {
    expect(getSystemLine('Kubernetes').id).toBe('platform');
    expect(getSystemLine('UnknownSystem').id).toBe('platform');
    expect(getSystemLine(undefined).id).toBe('platform');
    expect(getSystemLine(null).id).toBe('platform');
  });

  it('defines the five canonical categories with hex colours', () => {
    expect(Object.keys(CATEGORY_LINES)).toEqual([
      'messaging',
      'identity',
      'data',
      'observability',
      'platform',
    ]);
    for (const line of Object.values(CATEGORY_LINES)) {
      expect(line.color).toMatch(/^#[0-9A-Fa-f]{6}$/);
    }
  });
});
